/**
 * Hands — task-gated UI state machine (pure, testable without a browser).
 *
 * Modes:
 *   'bar'  — slim idle pill. No conversation, nothing on screen.
 *   'chat' — normal conversation (greetings, questions). The bar never enters
 *            execution position for plain chat, no matter what was said.
 *   'pet'  — compact execution state. ONLY entered when a real task is
 *            recognized POST-HOC from stream signals: SSE `tool_call`,
 *            `lane`, `lane_tool`, `delegated` events, or an explicit
 *            task-intent field (`type === 'desktop_task'` in the legacy
 *            classifier response), or the desktop agent launching.
 *
 * The reducer never blocks on anything: task recognition is decided from
 * events that arrive AFTER voice/text already started streaming.
 *
 * CommonJS so `node tests/check-hands-machine.js` can require it directly;
 * webpack/babel imports it fine from React.
 */

const LANE_DONE = 'done';
const LANE_ERROR = 'error';
const LANE_ACTIVE = ['idle', 'running', 'held', 'verified', 'steered'];

function laneFromCallId(callId) {
  const m = /^call_(ln[0-9a-f]{8})_/i.exec(callId || '');
  return m ? m[1] : null;
}

function shortLabel(name, args) {
  if (!name) return '';
  const a = args || {};
  const target = a.url || a.file_path || a.target || a.app_name || a.text || a.element_id || '';
  const t = String(target).replace(/\s+/g, ' ').trim();
  return t ? name + ' \u00b7 ' + t.slice(0, 42) : name;
}

function initialState(extra) {
  return Object.assign({
    mode: 'bar',
    chat: [],                 // [{role:'user'|'hands'|'system', text, streaming?}]
    lanes: {},                // laneId -> {id,status,currentTool,calls,done,errors,label}
    laneOrder: [],
    calls: {},                // callId -> {call_id,lane,state,to,seq,audioMode,transcript:[{speaker,text}]}
    callOrder: [],
    currentCall: null,        // call_id of the most recent/active call lane
    toolsTotal: 0,
    toolsDone: 0,
    toolsError: 0,
    currentTool: null,        // last tool_call name for the pet line
    taskTitle: null,          // collapse title in the listview / pet
    taskStartedAt: null,
    pendingClientTools: 0,    // tool results the desktop agent still owes
    delegated: false,
    lastEventWasTool: false,
    turnActive: false,
    showSuggestions: false,
  }, extra || {});
}

function touchLane(state, laneId, patch) {
  const id = laneId || 'ln-main';
  const lanes = Object.assign({}, state.lanes);
  let laneOrder = state.laneOrder;
  if (!lanes[id]) {
    lanes[id] = { id: id, status: 'running', currentTool: null, calls: 0, done: 0, errors: 0, label: null };
    laneOrder = laneOrder.concat([id]);
  } else {
    lanes[id] = Object.assign({}, lanes[id], patch || {});
    patch = null;
  }
  if (patch) Object.assign(lanes[id], patch);
  return { lanes: lanes, laneOrder: laneOrder };
}

/**
 * reduce(state, event) -> new state
 * Event kinds:
 *  {kind:'user_text', text}                          local echo, zero network first
 *  {kind:'delta', text}                              streamed voice/L text chunk (chat or exec)
 *  {kind:'chat_reply', text}                         full inquiry reply (post-hoc, NOT a task)
 *  {kind:'task_recognized', source, title?}          explicit task-intent signal, any source
 *  {kind:'tool_call', id?, lane?, name, arguments?}  one hop of an R-line -> enter pet
 *  {kind:'tool_result', tool_call_id?, lane?, name?, status?, executed_in?}
 *  {kind:'lane', ...}                                sawii_event row (beat/hold/verify/steer)
 *  {kind:'lane_tool', name?, lane?, ...}             lane-level tool row
 *  {kind:'delegated'}                                R handed a batch to a host agent
 *  {kind:'call_event', callKind?, event}             call lane frame: call_status|call_tone|call_transcript|call_audio
 *  {kind:'call_audio_mode', mode?, call_id?}         audio <-> live-transcript toggle (UI-local)
 *  {kind:'agent_activity', message, action?}         legacy desktop-agent TASKER_EVENT
 *  {kind:'agent_exit'}                               desktop agent process ended
 *  {kind:'turn_done', text?, tools_pending_client?}  one /act turn closed
 *  {kind:'task_finished'}                            whole task done -> leave pet
 *  {kind:'collapse'}                                 operator asked for the slim bar
 *  {kind:'show_suggestions', value}                  suggestions panel toggle
 */
function reduce(state, ev) {
  if (!ev || !ev.kind) return state;
  switch (ev.kind) {

    case 'user_text': {
      const chat = state.chat.concat([{ role: 'user', text: ev.text || '' }]);
      // Plain conversation. Deliberately NO mode escalation here.
      return Object.assign({}, state, { chat: chat, mode: state.mode === 'pet' ? 'pet' : 'chat' });
    }

    case 'delta': {
      const chat = state.chat.slice();
      const last = chat[chat.length - 1];
      if (last && last.role === 'hands' && last.streaming) {
        chat[chat.length - 1] = Object.assign({}, last, { text: (last.text || '') + (ev.text || '') });
      } else {
        chat.push({ role: 'hands', text: ev.text || '', streaming: true });
      }
      // Text flowing is NOT a task signal. Pet is only entered on tool/lane/delegation.
      return Object.assign({}, state, {
        chat: chat,
        mode: state.mode === 'bar' ? 'chat' : state.mode,
      });
    }

    case 'chat_reply': {
      const chat = state.chat.concat([{ role: 'hands', text: ev.text || '', streaming: false }]);
      return Object.assign({}, state, { chat: chat, mode: state.mode === 'pet' ? 'pet' : 'chat' });
    }

    case 'task_recognized': {
      return Object.assign({}, state, {
        mode: 'pet',
        taskTitle: ev.title || state.taskTitle || shortFromChat(state),
        taskStartedAt: state.taskStartedAt || Date.now(),
        turnActive: true,
      });
    }

    case 'tool_call': {
      const laneId = ev.lane || laneFromCallId(ev.id) || 'ln-main';
      const args = parseArgs(ev.arguments);
      const label = shortLabel(ev.name, args);
      const laneRef = touchLane(state, laneId);
      const lanes = Object.assign({}, laneRef.lanes);
      const prev = lanes[laneId];
      const lane = Object.assign({}, prev, {
        status: 'running',
        currentTool: ev.name || prev.currentTool,
        calls: (prev.calls || 0) + 1,
        label: label || prev.label,
      });
      lanes[laneId] = lane;
      return Object.assign({}, state, {
        lanes: lanes,
        laneOrder: laneRef.laneOrder,
        mode: 'pet',                       // POST-HOC gate: a tool call IS the task
        taskStartedAt: state.taskStartedAt || Date.now(),
        taskTitle: state.taskTitle || shortFromChat(state),
        toolsTotal: state.toolsTotal + 1,
        currentTool: ev.name || state.currentTool,
        lastEventWasTool: true,
        turnActive: true,
      });
    }

    case 'lane_tool': {
      const laneId = ev.lane || laneFromCallId(ev.id) || null;
      const laneRef = touchLane(state, laneId);
      const lanes = Object.assign({}, laneRef.lanes);
      const id = laneId || 'ln-main';
      lanes[id] = Object.assign({}, lanes[id], {
        currentTool: ev.name || lanes[id].currentTool,
        label: ev.name ? shortLabel(ev.name, ev.arguments ? parseArgs(ev.arguments) : ev) : lanes[id].label,
      });
      return Object.assign({}, state, {
        lanes: lanes, laneOrder: laneRef.laneOrder,
        mode: 'pet', currentTool: ev.name || state.currentTool, lastEventWasTool: true, turnActive: true,
      });
    }

    case 'tool_result': {
      const laneId = ev.lane || laneFromCallId(ev.tool_call_id) || 'ln-main';
      const laneRef = touchLane(state, laneId);
      const lanes = Object.assign({}, laneRef.lanes);
      const failed = ev.status === 'error';
      const lane = Object.assign({}, lanes[laneId], {
        status: failed ? LANE_ERROR : LANE_DONE,
        done: (lanes[laneId].done || 0) + (failed ? 0 : 1),
        errors: (lanes[laneId].errors || 0) + (failed ? 1 : 0),
        currentTool: null,
      });
      lanes[laneId] = lane;
      return Object.assign({}, state, {
        lanes: lanes, laneOrder: laneRef.laneOrder,
        toolsDone: state.toolsDone + 1,
        toolsError: state.toolsError + (failed ? 1 : 0),
        lastEventWasTool: true,
      });
    }

    case 'lane': {
      // sawii_event rows carry {lane|id, type|status ...} — beat/hold/verify/steer.
      const raw = ev.event || ev;
      const laneId = raw.lane || raw.ln || raw.id || null;
      const kind = String(raw.type || raw.status || raw.kind || '');
      const laneRef = touchLane(state, laneId);
      const lanes = Object.assign({}, laneRef.lanes);
      const id = laneId || 'ln-main';
      let status = lanes[id].status;
      if (/hold/i.test(kind)) status = 'held';
      else if (/verify/i.test(kind)) status = 'verified';
      else if (/steer/i.test(kind)) status = 'steered';
      else if (/done|finish|close/i.test(kind)) status = LANE_DONE;
      else if (/^beat$/i.test(kind) || /open|start/i.test(kind)) status = 'running';
      lanes[id] = Object.assign({}, lanes[id], { status: status });
      return Object.assign({}, state, {
        lanes: lanes, laneOrder: laneRef.laneOrder,
        mode: 'pet', lastEventWasTool: false, turnActive: true,
      });
    }

    case 'delegated': {
      return Object.assign({}, state, {
        mode: 'pet', delegated: true, lastEventWasTool: false, turnActive: true,
      });
    }

    case 'call_event': {
      // One lane call-LIVE frame from the call SSE stream (backend
      // utils/call_lane.py rows pass through with their frame name):
      //   call_status | call_tone | call_transcript | call_audio.
      // Existing lane statuses are REUSED: dialing/ringing/connected =>
      // 'running' (held => 'held', ended => done, failed => error) — no
      // new event kinds and the pet keeps one visual language.
      const d = ev.event || ev.data || {};
      const callId = d.call_id || 'call-main';
      const laneId = d.lane || 'ln-main';
      const kind = ev.callKind || d.kind || 'call_status';
      const calls = Object.assign({}, state.calls);
      let callOrder = state.callOrder;
      if (!calls[callId]) {
        calls[callId] = { call_id: callId, lane: laneId, state: 'starting', to: d.to || null,
                          seq: 0, audioMode: 'audio', transcript: [], tones: 0 };
        callOrder = callOrder.concat([callId]);
      } else {
        calls[callId] = Object.assign({}, calls[callId]);
      }
      const call = calls[callId];
      if (typeof d.seq === 'number') call.seq = Math.max(call.seq, d.seq);

      if (kind === 'call_status') {
        call.state = d.state || call.state;
        if (d.to) call.to = d.to;
      } else if (kind === 'call_transcript') {
        call.transcript = call.transcript.concat(
          [{ speaker: d.speaker || 'them', text: d.text || '' }]).slice(-60);
      } else if (kind === 'call_tone') {
        call.tones = (call.tones || 0) + 1;
      } else if (kind === 'call_audio') {
        call.lastAudioSeq = d.seq || call.seq;
      }

      // Mirror the call state onto the owning LANE so the lane chips / active
      // count / shimmer stay a single system.
      const laneRef = touchLane(state, laneId);
      const lanes = Object.assign({}, laneRef.lanes);
      const laneStatus = call.state === 'ended' ? LANE_DONE
        : call.state === 'failed' ? LANE_ERROR
        : call.state === 'held' ? 'held' : 'running';
      lanes[call.lane] = Object.assign({}, lanes[call.lane], {
        status: laneStatus,
        label: 'call \u00b7 ' + String(call.to || '').slice(0, 18),
        currentTool: call.state,
      });
      const activeCall = call.state !== 'ended' && call.state !== 'failed';
      const st = Object.assign({}, state, {
        calls: calls, callOrder: callOrder,
        lanes: lanes, laneOrder: laneRef.laneOrder,
        mode: 'pet',
        taskStartedAt: state.taskStartedAt || Date.now(),
        turnActive: activeCall ? true : state.turnActive,
        currentCall: callId,
      });
      return st;
    }

    case 'call_audio_mode': {
      // Operator toggle (audio <-> real-time transcript). Pure UI routing —
      // backend call events never change.
      const calls = Object.assign({}, state.calls);
      const id = ev.call_id || state.currentCall;
      if (id && calls[id]) calls[id] = Object.assign({}, calls[id], { audioMode: ev.mode || 'audio' });
      return Object.assign({}, state, { calls: calls });
    }

    case 'agent_activity': {
      // Legacy desktop-agent TASKER_EVENT stream: it only runs when a real task
      // is executing, so treat it as a task signal too (post-hoc, never pre-gated).
      const label = ev.message || shortLabel(ev.action, ev.params);
      const laneRef = touchLane(state, 'ln-desktop');
      const lanes = Object.assign({}, laneRef.lanes);
      lanes['ln-desktop'] = Object.assign({}, lanes['ln-desktop'], {
        status: 'running', label: label || lanes['ln-desktop'].label, currentTool: ev.action || null,
      });
      return Object.assign({}, state, {
        lanes: lanes, laneOrder: laneRef.laneOrder,
        mode: 'pet', currentTool: ev.action || state.currentTool,
        taskStartedAt: state.taskStartedAt || Date.now(),
        turnActive: true, lastEventWasTool: false,
      });
    }

    case 'agent_exit': {
      const chat = state.chat.concat([{ role: 'system', text: 'Execution finished \u2014 back to you.' }]);
      return Object.assign({}, state, { chat: chat, mode: 'chat', turnActive: false, currentTool: null });
    }

    case 'turn_done': {
      const pending = Array.isArray(ev.tools_pending_client)
        ? ev.tools_pending_client.length
        : (ev.tools_pending_client ? 1 : 0);
      const next = Object.assign({}, state, {
        pendingClientTools: pending,
        lastEventWasTool: false,
      });
      // Voice/text can already continue in chat regardless of this.
      return next;
    }

    case 'task_finished': {
      const chat = state.chat.concat([{ role: 'system', text: 'Task complete.' }]);
      return Object.assign({}, state, {
        chat: chat, mode: 'chat', turnActive: false, currentTool: null, pendingClientTools: 0,
      });
    }

    case 'collapse': {
      return Object.assign({}, state, { mode: 'bar', showSuggestions: false });
    }

    case 'show_suggestions': {
      return Object.assign({}, state, { showSuggestions: !!ev.value });
    }

    default:
      return state;
  }
}

function parseArgs(a) {
  if (!a) return {};
  if (typeof a === 'object') return a;
  try { return JSON.parse(a); } catch (e) { return {}; }
}

function shortFromChat(state) {
  const userMsg = state.chat.filter(function (m) { return m.role === 'user'; }).pop();
  const t = (userMsg && userMsg.text || state.taskTitle || 'Task').trim();
  if (!t) return 'Task';
  return t.length > 48 ? t.slice(0, 48) : t;
}

// ── Selectors ────────────────────────────────────────────────────────────────

function selectLanes(state) {
  return state.laneOrder.map(function (id) { return state.lanes[id]; });
}

function selectActiveLaneCount(state) {
  return selectLanes(state).filter(function (l) {
    return l.status !== LANE_DONE && l.status !== LANE_ERROR;
  }).length;
}

function selectProgress(state) {
  if (!state.toolsTotal) return 0;
  return Math.min(1, state.toolsDone / state.toolsTotal);
}

function selectIsShimmering(state) {
  // Shimmer while executing and there is (or may be) outstanding work.
  // Terminal lane results do NOT shimmer: once every call resolved
  // (toolsDone >= toolsTotal) and no lane stays active, the rail goes still.
  if (state.mode !== 'pet') return false;
  const outstanding = selectActiveLaneCount(state) > 0
    || state.pendingClientTools > 0
    || state.toolsDone < state.toolsTotal;
  // 'Planning…' window: delegated/pre-tool, nothing resolved yet.
  const planning = state.turnActive && state.toolsTotal === 0 && state.laneOrder.length === 0;
  return outstanding || planning;
}

// ── Call lane selectors (voice phone calls) ────────────────────────────────
// Call state lives on state.calls; the owning lane chip mirrors it. audioMode
// is a purely UI routing decision: 'audio' renders far-end frames as realtime
// speech, 'transcript' shows the same frames as realtime text instead. The
// backend frames are IDENTICAL in both modes.

function selectCalls(state) {
  return (state.callOrder || []).map(function (id) { return state.calls[id]; });
}

function selectActiveCall(state) {
  const open = selectCalls(state).filter(function (c) {
    return c.state !== 'ended' && c.state !== 'failed';
  });
  return open.length ? open[open.length - 1] : null;
}

const CALL_STATE_WORDS = {
  starting: 'Starting\u2026', dialing: 'Dialing\u2026', ringing: 'Ringing\u2026',
  connected: 'On call', held: 'On hold', unheld: 'On call',
  ended: 'Call ended', failed: 'Call failed',
};

function selectCallLabel(state) {
  const c = selectActiveCall(state) || selectCalls(state).slice(-1)[0];
  if (!c) return null;
  const w = CALL_STATE_WORDS[c.state] || c.state;
  return w + (c.to ? ' \u00b7 ' + c.to : '') + (c.audioMode === 'transcript' ? ' \u00b7 live text' : '');
}

// Human one-liner for the collapsed pet + the listview titles.
function selectStatusLine(state) {
  if (state.mode !== 'pet') return null;
  const activeCall = selectActiveCall(state);
  if (activeCall) {
    const w = CALL_STATE_WORDS[activeCall.state] || activeCall.state;
    const last = (activeCall.transcript || []).slice(-1)[0];
    const heard = last
      ? (last.speaker === 'them' ? 'them: ' : last.speaker === 'me' ? 'you\u2192model: ' : 'hands: ')
        + String(last.text || '').slice(0, 46)
      : '';
    const bits = ['call ' + w];
    if (activeCall.to) bits.push(activeCall.to);
    if (heard) bits.push(heard);
    return bits.join(' \u00b7 ');
  }
  const lanes = selectLanes(state);
  const active = selectActiveLaneCount(state);
  if (state.toolsTotal === 0 && lanes.length === 0) return 'Planning\u2026';
  const bits = [];
  if (active > 0) bits.push(active + (active === 1 ? ' lane' : ' lanes') + ' live');
  if (state.toolsDone > 0) bits.push(state.toolsDone + '/' + state.toolsTotal + ' steps');
  if (state.currentTool) bits.push('running ' + state.currentTool);
  if (state.pendingClientTools > 0) bits.push(state.pendingClientTools + ' on-device');
  return bits.length ? bits.join(' \u00b7 ') : 'Wrapping up\u2026';
}

module.exports = {
  initialState: initialState,
  reduce: reduce,
  laneFromCallId: laneFromCallId,
  selectLanes: selectLanes,
  selectActiveLaneCount: selectActiveLaneCount,
  selectProgress: selectProgress,
  selectIsShimmering: selectIsShimmering,
  selectStatusLine: selectStatusLine,
  selectCalls: selectCalls,
  selectActiveCall: selectActiveCall,
  selectCallLabel: selectCallLabel,
  CALL_STATE_WORDS: CALL_STATE_WORDS,
  shortLabel: shortLabel,
  LANE_ACTIVE: LANE_ACTIVE,
};
