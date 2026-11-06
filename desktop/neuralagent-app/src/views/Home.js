import React, { useEffect, useRef, useState } from 'react';
import { FiActivity, FiArrowUpRight, FiLayers, FiMic, FiMonitor, FiZap } from 'react-icons/fi';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import axios from '../utils/axios';
import constants from '../utils/constants';
import { setError, setLoadingDialog } from '../store';
import useHands from '../hooks/useHands';
import { createVoiceLane } from '../voice/voiceLane';

// Persona orchestrator prefix (backend/routers/aiagent/persona_orchestrator.py).
const PERSONA_BASE = constants.SERVER_URL + '/aiagent/persona';

export default function Home() {
  const [messageText, setMessageText] = useState('');
  const [thinkingMode, setThinkingMode] = useState(false);
  const [handsFree, setHandsFree] = useState(false);
  const accessToken = useSelector((state) => state.accessToken);
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const hands = useHands({ personaBaseUrl: PERSONA_BASE, accessToken: accessToken });
  const voiceRef = useRef(null);
  const composerRef = useRef(null);

  // Voice lane: operator-toggled hands-free channel — continuous capture with
  // RMS endpointing decides turn boundaries (no push-to-talk per message).
  useEffect(() => {
    const lane = createVoiceLane({ handsFree: true });
    const offU = lane.on('utterance', (u) => {
      const fn = composerRef.current;
      if (fn) fn(u.text); // fire-and-forget from the voice path
    });
    const offM = lane.on('level', (lv) => { if (typeof lv.rms === 'number') hands.setMicLevel(lv.rms); });
    voiceRef.current = lane;
    if (handsFree) lane.open().catch(() => {});
    return () => { offU(); offM(); lane.close(); voiceRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const lane = voiceRef.current;
    if (!lane) return;
    lane.setHandsFree(handsFree);
    if (handsFree) lane.open().catch(() => {}); else lane.close();
  }, [handsFree]);

  const createThread = async (textOverride) => {
    const task = (typeof textOverride === 'string' && textOverride.trim()) || messageText.trim();
    if (!task) return;

    setMessageText('');
    // Zero-latency rule: echo the user immediately; recognition of THIS turn
    // happens POST-HOC from classifier/stream signals — never before the reply.
    hands.dispatch({ kind: 'user_text', text: task });
    dispatch(setLoadingDialog(true));
    try {
      const response = await axios.post(
        '/threads',
        { task, extended_thinking_mode: thinkingMode },
        { headers: { Authorization: 'Bearer ' + accessToken } }
      );
      const data = response.data;
      if (data.type === 'desktop_task') {
        hands.dispatch({ kind: 'task_recognized', title: task });
      } else if (data.response) {
        hands.dispatch({ kind: 'chat_reply', text: data.response });
      }
      // Navigate to thread — Thread.js handles persona streaming from there.
      navigate('/threads/' + data.thread_id);
    } catch (error) {
      dispatch(setError(true, constants.GENERAL_ERROR));
      window.setTimeout(() => dispatch(setError(false, '')), 3500);
    } finally {
      dispatch(setLoadingDialog(false));
    }
  };
  composerRef.current = createThread;

  const handleTextEnterKey = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      createThread();
    }
  };

  useEffect(() => {
    const loadPreferences = async () => {
      try {
        const thinking = await window.electronAPI.getLastThinkingModeValue();
        const hf = await window.electronAPI.getHandsFreeValue();
        setThinkingMode(thinking === 'true');
        setHandsFree(hf !== 'false'); // hands-free default: ON
      } catch (e) { /* browser preview without the electron shell */ }
    };
    loadPreferences();
  }, []);

  useEffect(() => {
    if (window.electronAPI?.onAIAgentLaunch) {
      window.electronAPI.onAIAgentLaunch((threadId) => navigate('/threads/' + threadId));
    }
  }, [navigate]);

  return (
    <main className="tasker-home hands-home">
      {/* ═══ TASKER→HANDS NAMING SWEEP (user-visible strings in Home) ═══ */}
      <section className="tasker-hero">
        <div className="tasker-kicker"><FiActivity aria-hidden="true" /> Hands · the mind that acts</div>
        <h1>Put the desktop<br /><span>in motion.</span></h1>
        <p className="tasker-hero-copy">
          Say the outcome or type it. Hands talks instantly, then fans parallel
          persona lanes across your machine while the conversation keeps flowing.
        </p>

        <div className="tasker-system-strip" aria-label="Hands execution status">
          <div>
            <span className={hands.state.mode === 'pet' ? 'tasker-status-dot is-live' : 'tasker-status-dot'} aria-hidden="true" />
            <strong>{hands.state.mode === 'pet' ? 'Executing' : 'Ready'}</strong>
            <small>{hands.state.mode === 'pet' ? (hands.selectors.statusLine || 'live') : 'Persona connected'}</small>
          </div>
          <div><FiLayers aria-hidden="true" /><strong>Parallel lanes</strong><small>Every hop runs at once</small></div>
          <div><FiMonitor aria-hidden="true" /><strong>Screen-aware</strong><small>Boundary verification on</small></div>
        </div>
      </section>

      <form className="tasker-compose-card" onSubmit={(event) => { event.preventDefault(); createThread(); }}>
        <div className="tasker-compose-heading">
          <div>
            <label htmlFor="hands-command">What should happen?</label>
            <p>Use plain language — or just talk. Greetings stay chat; real work collapses into the pet.</p>
          </div>
          <span className="tasker-command-hint">Enter to run · Shift + Enter for a new line</span>
        </div>
        <textarea
          id="hands-command"
          className="tasker-command-input"
          placeholder="Open Chrome, find the latest project brief, and save a copy on my desktop…"
          rows={4}
          value={messageText}
          onChange={(event) => setMessageText(event.target.value)}
          onKeyDown={handleTextEnterKey}
          aria-describedby="hands-command-help"
          aria-label="Tell Hands what to do"
        />
        <div className="tasker-compose-actions">
          <div className="tasker-option-group" role="group" aria-label="Execution options">
            <button type="button"
                    className={'tasker-option' + (handsFree ? ' is-selected' : '')}
                    onClick={() => {
                      setHandsFree((v) => {
                        const nv = !v;
                        if (window.electronAPI?.setHandsFreeValue) window.electronAPI.setHandsFreeValue(String(nv));
                        return nv;
                      });
                    }}
                    aria-pressed={handsFree}
                    title="Hands-free: mic stays open continuously — no push-to-talk">
              <FiMic aria-hidden="true" /><span>Hands-free {handsFree ? 'on' : 'off'}</span>
            </button>
            <button type="button" className={'tasker-option' + (thinkingMode ? ' is-selected' : '')} onClick={() => setThinkingMode(!thinkingMode)}>
              <FiZap aria-hidden="true" /><span>Extended reasoning</span>
            </button>
          </div>
          <button className="tasker-submit" type="submit" disabled={!messageText.trim()}>
            <span>Run task</span><FiArrowUpRight aria-hidden="true" />
          </button>
        </div>
        <p id="hands-command-help" className="tasker-compose-note">
          Hands replies the moment you finish — task recognition happens after, from the stream itself.
        </p>

        {handsFree && (
          <div className="hands-mic-strip" aria-hidden="true">
            <span className="hands-mic-dot" />
            <span className="hands-mic-label">open channel · RMS endpointing</span>
          </div>
        )}
      </form>

      <section className="tasker-runbook" aria-label="How Hands works">
        <div className="tasker-section-label">The operating model</div>
        <div className="tasker-runbook-grid">
          <article><span>01</span><h2>Voice first</h2><p>One mind answers in your language — no pre-gates, no queueing before the reply.</p></article>
          <article><span>02</span><h2>Lane depth</h2><p>R1..Rn fan out inside a single turn; every lane streams back as it moves.</p></article>
          <article><span>03</span><h2>Visible speed</h2><p>The collapsed pet shows lanes live, current tool, and shimmer progress — speed made visible.</p></article>
        </div>
      </section>
    </main>
  );
}
