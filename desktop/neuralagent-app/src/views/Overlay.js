import React, { useEffect, useRef, useState } from 'react';
import { FiActivity, FiMic, FiMicOff, FiSend, FiSquare, FiZap } from 'react-icons/fi';
import { useSelector } from 'react-redux';
import axios from '../utils/axios';
import constants from '../utils/constants';
import useHands from '../hooks/useHands';
import ExecutionPet, { HandsBar } from '../components/ExecutionPet';
import { publishHandsStatus } from '../state/handsBus';
import { createVoiceLane } from '../voice/voiceLane';

// URL of the persona orchestrator (backend router prefix /aiagent/persona).
const PERSONA_BASE = constants.SERVER_URL + '/aiagent/persona';

/**
 * Overlay — the always-on desktop surface of Hands.
 *
 * Golden rule: the *shape* of the surface (bar vs pet) is decided POST-HOC from
 * stream events. Typing or speaking "hi" only ever shows chat — no execution
 * collapse. A `tool_call`/`lane`/`delegated` frame, or the legacy classifier's
 * desktop_task answer, or the desktop agent launching — escalates to the pet.
 */
export default function Overlay() {
  const [expanded, setExpanded] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [messageText, setMessageText] = useState('');
  const [loading, setLoading] = useState(false);
  const [runningThreadId, setRunningThreadId] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [thinkingMode, setThinkingMode] = useState(false);
  const [handsFree, setHandsFree] = useState(true);   // operator toggle — default = continuous
  const [listening, setListening] = useState(false);
  const accessToken = useSelector((state) => state.accessToken);

  const hands = useHands({ personaBaseUrl: PERSONA_BASE, accessToken: accessToken });
  const voiceRef = useRef(null);
  const voiceTurnsRef = useRef([]);
  const lastThreadRef = useRef(null);
  // When the call strip's TALK button is armed, the NEXT utterance is a steer
  // for this call id instead of a normal turn. Critical boundary: the mic only
  // ever produces text for the model side — it is never routed into call audio.
  const steerCallRef = useRef(null);

  /* ---------------- voice lane: open channel, zero-needed button presses ---------------- */

  useEffect(() => {
    const lane = createVoiceLane({ handsFree: true });
    const offU = lane.on('utterance', (u) => {
      // Critical path = chat send only. Classification/persona ingestion kicked
      // off as fire-and-forget below; nothing here awaits before we react to text.
      dispatchUser(u.text);
    });
    const offS = lane.on('state', (st) => {
      if (st.listening !== undefined) setListening(Boolean(st.listening));
      if (st.tts !== undefined) setListening(!st.tts && listeningRef.current);
    });
    const offL = lane.on('level', (lv) => {
      if (typeof lv.rms === 'number') hands.setMicLevel(lv.rms);
    });
    voiceRef.current = lane;
    hands.setVoiceSupported(lane.supports());

    // Hands speaks every assistant reply in the open channel (TTS lane).
    const speakReply = (text) => { if (text && modeRef.current !== 'muted') lane.speak(text); };
    speakRef.current = speakReply;

    if (!handsFree) lane.close(); else lane.open().catch(() => {});
    return () => { offU(); offS(); offL(); lane.close(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const listeningRef = useRef(false);
  listeningRef.current = listening;
  const modeRef = useRef('hands-free');
  const speakRef = useRef(function () {});

  useEffect(() => {
    const lane = voiceRef.current;
    if (!lane) return;
    if (handsFree) lane.open().catch(() => {});
    else { lane.setHandsFree(false); lane.close(); }
  }, [handsFree]);

  /* ---------------- assistant voice -> TTS while streaming deltas ---------------- */

  useEffect(() => {
    const last = hands.state.chat[hands.state.chat.length - 1];
    if (last && last.role === 'hands' && last.text) speakRef.current(last.streaming ? '' : last.text);
    // Sentence-ish live read while streaming: speak completed sentences the moment they land.
    if (last && last.role === 'hands' && last.streaming) {
      const tail = (last.text || '');
      const splitAt = tail.lastIndexOf('. ');
      if (splitAt > 24 && splitAt !== spokeUpToRef.current) {
        spokeUpToRef.current = splitAt;
        speakRef.current(tail.slice(0, splitAt + 1));
      }
    }
  }, [hands.state.chat]);
  const spokeUpToRef = useRef(-1);

  /* ---------------- machine -> OS window + listview titles ---------------- */

  useEffect(() => {
    const mode = hands.state.mode;
    const api = window.electronAPI || {};
    if (api.setOverlayMode) api.setOverlayMode(mode);
    publishHandsStatus({
      online: Boolean(accessToken),
      mode: mode,
      title: hands.state.taskTitle,
      statusLine: hands.selectors.statusLine,
      threads: voiceTurnsRef.current.slice(-12).map((t) => ({ user: t.user, hands: (t.hands || '').slice(0, 90) })),
    });
  }, [hands.state, expanded, accessToken]);

  useEffect(() => {
    lastThreadRef.current = runningThreadId;
    if (runningThreadId) hands.dispatch({ kind: 'task_recognized' });
  }, [runningThreadId, hands.dispatch]);

  /* ---------------- user turns (text + voice share one path) ---------------- */

  const dispatchUser = (text) => {
    if (!text) return;
    // Mid-call steering wins over the normal turn path: one utterance, one lane.
    const steerCall = steerCallRef.current;
    if (steerCall && hands.call?.steer) {
      // The lane's own SSE echoes this as speaker 'me' (utils/call_lane.py
      // control('steer')) — no optimistic local row needed, no duplicate.
      hands.call.steer(text, steerCall).catch(() => {});
      hands.call.onTalkChange?.(steerCall, false);
      return;
    }
    hands.dispatch({ kind: 'user_text', text });
    const turn = { user: text, hands: '', taskSignal: false };
    voiceTurnsRef.current = voiceTurnsRef.current.concat([turn]).slice(-12);
    // Fast: local echo + optimistic chat render; heavy work is fire-and-forget.
    if (runningThreadId) {
      hands.streamAct(runningThreadId, { text });
    } else {
      optimisticSend(text);
    }
  };

  const optimisticSend = async (text) => {
    setLoading(true);
    try {
      const response = await axios.post('/threads', {
        task: text,
        extended_thinking_mode: thinkingMode,
      }, { headers: { Authorization: 'Bearer ' + accessToken } });
      const data = response.data;
      // Recognition is POST-HOC: the reply text was already streamed/echoed above
      // (or will be via the classifier response below) before this shape decision.
      const reply = (data && data.response) || '';
      if (data.type !== 'desktop_task' && reply) {
        hands.dispatch({ kind: 'chat_reply', text: reply });
        spokeUpToRef.current = -1;
      }
      if (data.type === 'desktop_task') {
        hands.dispatch({ kind: 'task_recognized', title: text });
        threadIdRef.current = data.thread_id;
        setRunningThreadId(data.thread_id);
        // Persona streaming starts via hands.streamAct on the next user turn
        // (dispatchUser checks runningThreadId). No legacy agent launch needed.
      } else if (data.thread_id) {
        threadIdRef.current = data.thread_id;
      }
    } catch (error) {
      if (error.response && error.response.status === constants.status.UNAUTHORIZED) window.location.reload();
      else hands.dispatch({ kind: 'chat_reply', text: '\u26a0 Could not reach the backend.' });
    } finally {
      setLoading(false);
    }
  };

  const threadIdRef = useRef(null);

  /* ---------------- legacy suggestion + agent lifecycle (keep working) ---------------- */

  const getSuggestions = async () => {
    try {
      const result = await window.electronAPI.getSuggestions(
        constants.SERVER_URL
      );
      setSuggestions(result.suggestions || []);
    } catch { setSuggestions([]); }
  };

  const cancelRunningTask = async () => {
    const tid = runningThreadId || threadIdRef.current;
    if (!tid) return;
    setLoading(true);
    try {
      await axios.post('/threads/' + tid + '/cancel_task', {}, { headers: { Authorization: 'Bearer ' + accessToken } }).catch(() => {});
      window.electronAPI.stopAIAgent();
      hands.dispatch({ kind: 'task_finished' });
      setRunningThreadId(null);
    } finally { setLoading(false); }
  };

  const toggleOverlay = () => {
    if (!expanded) {
      window.electronAPI.expandOverlay(true);
      setExpanded(true);
      setShowSuggestions(runningThreadId === null);
      if (runningThreadId === null && suggestions.length === 0) getSuggestions();
    } else {
      window.electronAPI.minimizeOverlay();
      setExpanded(false);
      setSuggestions([]);
      setShowSuggestions(false);
    }
  };

  useEffect(() => {
    if (window.electronAPI?.onAIAgentLaunch) {
      window.electronAPI.onAIAgentLaunch((threadId) => {
        window.electronAPI.expandOverlay(false);
        setExpanded(true);
        setRunningThreadId(threadId);
        setShowSuggestions(false);
      });
    }
    if (window.electronAPI?.onAIAgentExit) {
      window.electronAPI.onAIAgentExit(() => {
        setRunningThreadId(null);
        window.electronAPI.expandOverlay(true);
        setExpanded(true);
        setShowSuggestions(true);
        setSuggestions([]);
        getSuggestions();
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const loadPreferences = async () => {
      try {
        const thinking = await window.electronAPI.getLastThinkingModeValue();
        const hf = await window.electronAPI.getHandsFreeValue && await window.electronAPI.getHandsFreeValue();
        setThinkingMode(thinking === 'true');
        if (hf !== undefined && hf !== null) setHandsFree(hf !== 'false');
      } catch (e) { /* browser preview without electron */ }
    };
    loadPreferences();
  }, []);

  const sendChat = () => {
    const text = messageText.trim();
    if (!text || loading) return;
    setMessageText('');
    dispatchUser(text);
  };

  const mode = hands.state.mode;
  const inPet = mode === 'pet' || Boolean(runningThreadId);

  // The pet's TALK button arms/disarms mid-call steering for the voice lane.
  useEffect(function () {
    if (!hands.call) return;
    hands.call.setTalkHandler(function (callId, active) {
      steerCallRef.current = active ? callId : null;
    });
  }, [hands.call]);

  return (
    <div className={'tasker-overlay ' + (expanded ? 'is-expanded' : 'is-compact') + (inPet ? ' hands-in-pet' : '')}>
      {!expanded && !inPet && (
        <HandsBar
          onExpand={toggleOverlay}
          micLevel={hands.micLevel}
          listening={listening && handsFree}
          running={false}
          title={constants.APP_NAME}
        />
      )}
      {!expanded && inPet && (
        <ExecutionPet state={hands.state} onStop={cancelRunningTask} compact call={hands.call} />
      )}

      {expanded && (
        <>
          <div className="tasker-overlay-bar">
            <button className="tasker-overlay-brand" onClick={toggleOverlay} aria-label={expanded ? 'Minimize Hands' : 'Expand Hands'}>
              <span className="tasker-overlay-mark">H</span>
              {/* A task only collapses the surface AFTER recognition; chat never does. */}
              {inPet ? <ExecutionPet state={hands.state} onStop={cancelRunningTask} compact call={hands.call} /> : <span>Hands</span>}
            </button>
            <div className="tasker-overlay-chat" aria-live="polite">
              {hands.state.chat.slice(-6).map((m, i) => (
                <div key={i} className={'hands-chat-line is-' + m.role}>
                  {m.role === 'user' ? 'You: ' : m.role === 'hands' ? 'Hands: ' : ''}{m.text}
                  {m.streaming ? ' ▍' : ''}
                </div>
              ))}
            </div>
            {!loading && !runningThreadId && mode !== 'pet' && (
              <div className="tasker-overlay-options">
                <button className={'tasker-overlay-option ' + (handsFree ? 'is-selected' : '')}
                        onClick={() => { setHandsFree((v) => { const nv = !v; if (window.electronAPI.setHandsFreeValue) window.electronAPI.setHandsFreeValue(String(nv)); return nv; }); }}
                        aria-label="Toggle hands-free voice (continuous, no push-to-talk)"
                        title={handsFree ? 'Hands-free voice ON' : 'Voice off'}>
                  {handsFree ? <FiMic /> : <FiMicOff />}
                </button>
                <button className={'tasker-overlay-option ' + (thinkingMode ? 'is-selected' : '')} onClick={() => setThinkingMode(!thinkingMode)} aria-label="Toggle extended reasoning"><FiZap /></button>
                <input
                  className="tasker-overlay-input"
                  value={messageText}
                  onChange={(event) => setMessageText(event.target.value)}
                  placeholder="Say or type a task…"
                  onKeyDown={(event) => { if (event.key === 'Enter') sendChat(); }}
                  aria-label="Hands command"
                />
                <button className="tasker-overlay-send" onClick={sendChat} aria-label="Talk to Hands"><FiSend /></button>
              </div>
            )}
            {loading && <span className="tasker-overlay-loading" aria-label="Hands is working"><FiActivity /></span>}
            {(runningThreadId || mode === 'pet') && (
              <button className="tasker-overlay-stop" onClick={cancelRunningTask} disabled={loading} aria-label="Stop task"><FiSquare /></button>
            )}
          </div>
          {showSuggestions && mode !== 'pet' && (
            <div className="tasker-overlay-suggestions" aria-label="Suggested tasks">
              {suggestions.length === 0 ? (
                <div className="tasker-overlay-empty">Reading the current workspace…</div>
              ) : suggestions.map((suggestion, index) => (
                <button key={index} className="tasker-overlay-suggestion" onClick={() => dispatchUser(suggestion.ai_prompt)}>
                  <span>{suggestion.title}</span><FiSend aria-hidden="true" />
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
