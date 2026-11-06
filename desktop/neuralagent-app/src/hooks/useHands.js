/**
 * Hands — the single connective tissue between event sources and the UI state
 * machine. Sources:
 *   - persona SSE (/aiagent/persona/{tid}/act) — delta/tool_call/lane/...
 *   - legacy desktop agent TASKER_EVENTs (Electron IPC 'ai-agent-status')
 *   - voice lane utterances (voiceLane.js) — handed over fire-and-forget
 *
 * Nothing here awaits on the conversation path: recognition is derived from
 * events AFTER text/voice started (reducer decides bar/chat/pet post-hoc).
 */
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import machine from '../state/handsMachine';
import streamPersonaAct, { streamCallEvents, callControl } from '../utils/personaClient';
import { createCallAudio } from '../call/callAudio';

const { initialState, reduce } = machine;

export default function useHands(options) {
  options = options || {};
  const [state, dispatch] = useReducer(reduce, undefined, function () { return initialState(); });
  const [micLevel, setMicLevel] = useState(0);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState(false);
  const abortRef = useRef(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  // ── call lanes (voice phone calls) ────────────────────────────────────────
  const callStreamsRef = useRef({});        // call_id -> AbortController
  const callTidRef = useRef({});           // call_id -> thread id (for controls)
  const callAudioRef = useRef(null);        // lazily-created local audio engine
  const talkHandlerRef = useRef(null);      // view's voice lane: (callId,on)->arm steer

  function ensureCallAudio() {
    if (callAudioRef.current) return callAudioRef.current;
    try {
      callAudioRef.current = createCallAudio({ mode: 'audio' });
    } catch (e) { callAudioRef.current = null; }
    return callAudioRef.current;
  }

  const dispatchCallFrame = useCallback(function (frame) {
    const d = frame.data || {};
    const kind = frame.event;
    if (kind === 'call_error') {
      dispatch({ kind: 'chat_reply', text: '\u26a0 ' + (d.message || 'Call stream error') });
      return;
    }
    if (kind !== 'call_status' && kind !== 'call_tone' &&
        kind !== 'call_transcript' && kind !== 'call_audio') return;
    dispatch({ kind: 'call_event', callKind: kind, event: d });
    // Audio legs only ever feed the LOCAL render engine. Nothing from the mic
    // passes through here — hard boundary: user -> model via steer() text only.
    const aud = ensureCallAudio();
    if (aud && (kind === 'call_audio' || kind === 'call_tone')) {
      aud.feed(Object.assign({ kind: kind }, d));
    }
  }, []);

  const attachCallLane = useCallback(function (tid, info) {
    const callId = info && info.call_id;
    if (!callId || callStreamsRef.current[callId]) return;
    callTidRef.current[callId] = tid;
    const ctrl = new AbortController();
    callStreamsRef.current[callId] = ctrl;
    streamCallEvents(tid, callId, options.accessToken, dispatchCallFrame, ctrl.signal,
      options.personaBaseUrl).catch(function (err) {
      if (err && err.name !== 'AbortError') dispatchCallFrame({ event: 'call_error', data: { message: String(err.message || err) } });
    }).finally(function () { delete callStreamsRef.current[callId]; });
  }, [options.accessToken, options.personaBaseUrl, dispatchCallFrame]);

  useEffect(function () {
    return function () {
      Object.keys(callStreamsRef.current).forEach(function (cid) {
        try { callStreamsRef.current[cid].abort(); } catch (e) {}
      });
      if (callAudioRef.current) callAudioRef.current.stop();
    };
  }, []);

  // legacy desktop-agent progress -> pet-mounted activity (agent only runs for real tasks)
  useEffect(function () {
    if (!window.electronAPI || !window.electronAPI.onAIAgentStatus) return undefined;
    return window.electronAPI.onAIAgentStatus(function (event) {
      dispatch({ kind: 'agent_activity', message: event.message, action: event.action, params: event.params });
    });
  }, []);

  useEffect(function () {
    if (!window.electronAPI || !window.electronAPI.onAIAgentExit) return undefined;
    return window.electronAPI.onAIAgentExit(function () { dispatch({ kind: 'agent_exit' }); });
  }, []);

  const mapPersonaEvent = useCallback(function (frame) {
    const d = frame.data || {};
    switch (frame.event) {
      case 'delta': return { kind: 'delta', text: d.text || '' };
      case 'tool_call': return { kind: 'tool_call', id: d.id, lane: d.lane, name: d.name, arguments: d.arguments };
      case 'tool_result': return { kind: 'tool_result', tool_call_id: d.tool_call_id, lane: d.lane, name: d.name, status: d.status, executed_in: d.executed_in };
      case 'lane': return { kind: 'lane', event: d };
      case 'lane_tool': return { kind: 'lane_tool', event: d };
      case 'delegated': return { kind: 'delegated' };
      case 'done': return { kind: 'turn_done', text: d.text, tools_pending_client: d.tools_pending_client };
      case 'error': return { kind: 'chat_reply', text: '\u26a0 ' + (d.message || 'Persona stream error') };
      default: return null;
    }
  }, []);

  /** Fire one /act turn; events flow into the machine as they arrive. Never awaited by callers. */
  const streamAct = useCallback(async function (tid, payload) {
    if (abortRef.current) { try { abortRef.current.abort(); } catch (e) { /* already done */ } }
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      await streamPersonaAct(options.personaBaseUrl, tid, options.accessToken, payload, function (frame) {
        // start_call's tool_result carries {call_id, stream_path…} — attach the
        // lane's own SSE exactly like the agent attaches execution streams.
        if (frame.event === 'tool_result' && frame.data && frame.data.name === 'start_call') {
          try {
            const parsed = JSON.parse(frame.data.result || '{}');
            if (parsed && parsed.ok && parsed.call_id) attachCallLane(tid, parsed);
          } catch (e) { /* result text is not JSON — ignore */ }
        }
        const ev = mapPersonaEvent(frame);
        if (ev) dispatch(ev);
      }, ctrl.signal);
    } catch (err) {
      if (err && err.name !== 'AbortError') dispatch({ kind: 'chat_reply', text: '\u26a0 ' + String(err.message || err) });
    }
  }, [options.personaBaseUrl, options.accessToken, mapPersonaEvent, attachCallLane]);

  // ── call controls (pet buttons / voice intent route here) ────────────────
  const callApi = useMemo(function () {
    function active() {
      const open = machine.selectCalls(state).filter(function (c) {
        return c.state !== 'ended' && c.state !== 'failed';
      });
      return open[open.length - 1] || null;
    }
    function send(action, text, callId) {
      const c = callId ? machine.selectCalls(state).filter(function (x) { return x.call_id === callId; })[0] : active();
      const id = c && c.call_id;
      const tid = id ? callTidRef.current[id] : null;
      if (!id || !tid) return Promise.reject(new Error('no active call lane'));
      // speak = the ONLY audio Hands sends to the far end; steer = text to
      // the model side only. Both fire-and-forget; the SSE stream reflects
      // authoritative state, so optimistic UI stays minimal.
      if (action === 'speak' || action === 'steer') {
        try {
          const aud = ensureCallAudio();
          if (aud && action === 'speak') aud.feed({ kind: 'call_audio', speaker: 'hands', format: 'queue:say', text: text });
        } catch (e) { /* cosmetic */ }
      }
      return callControl(tid, id, options.accessToken, action, text, options.personaBaseUrl)
        .then(function (res) {
          if (action === 'hangup') {
            dispatch({ kind: 'call_event', callKind: 'call_status',
              event: { call_id: id, lane: c.lane, state: 'ended', reason: 'hangup', seq: (c.seq || 0) + 1 } });
          }
          return res;
        });
    }
    return {
      get activeCallId() { const c = active(); return c && c.call_id; },
      hangup: function (callId) { return send('hangup', '', callId); },
      hold: function (callId) { return send('hold', '', callId); },
      unhold: function (callId) { return send('unhold', '', callId); },
      steer: function (text, callId) {
        // THE hard boundary: user utterance -> control text (model side only).
        // Nothing here sends mic audio anywhere; audio legs are read-only.
        return send('steer', text, callId);
      },
      speak: function (text, callId) { return send('speak', text, callId); },
      setAudioMode: function (mode, callId) {
        dispatch({ kind: 'call_audio_mode', mode: mode === 'transcript' ? 'transcript' : 'audio', call_id: callId });
      },
      /** The host view registers (callId, active) here so its voice lane routes
       *  the NEXT utterance to steer() while TALK is armed. The mic NEVER
       *  reaches the call — steer is text into the model side only. */
      setTalkHandler: function (fn) { talkHandlerRef.current = fn; },
      onTalkChange: function (callId, active) {
        const h = talkHandlerRef.current;
        if (h) h(callId, active);
      },
    };
  }, [state, options.accessToken, options.personaBaseUrl]);

  function setCallAudioMode(mode, callId) {
    // UI-local routing toggle; the state effect below re-syncs the audio engine.
    dispatch({ kind: 'call_audio_mode', mode: mode === 'transcript' ? 'transcript' : 'audio', call_id: callId });
  }

  // When the machine says transcript mode, mute the audio legs.
  useEffect(function () {
    const c = machine.selectActiveCall(state);
    const aud = callAudioRef.current;
    if (!aud) return;
    aud.setMode(c && c.audioMode === 'transcript' ? 'transcript' : 'audio');
    aud.setMuted(Boolean(c && c.state === 'held'));
  }, [state]);

  const selectors = useMemo(function () {
    return {
      lanes: machine.selectLanes(state),
      activeLanes: machine.selectActiveLaneCount(state),
      progress: machine.selectProgress(state),
      shimmer: machine.selectIsShimmering(state),
      statusLine: machine.selectStatusLine(state),
      callLabel: machine.selectCallLabel(state),
      activeCall: machine.selectActiveCall(state),
    };
  }, [state]);

  return {
    state: state,
    dispatch: dispatch,
    streamAct: streamAct,
    selectors: selectors,
    call: callApi,
    setCallAudioMode: setCallAudioMode,
    micLevel: micLevel,
    setMicLevel: setMicLevel,
    voiceOpen: voiceOpen,
    setVoiceOpen: setVoiceOpen,
    voiceSupported: voiceSupported,
    setVoiceSupported: setVoiceSupported,
  };
}
