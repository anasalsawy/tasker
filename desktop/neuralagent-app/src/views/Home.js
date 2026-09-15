import React, { useEffect, useState } from 'react';
import { FiActivity, FiArrowUpRight, FiLayers, FiMonitor, FiMoon, FiZap } from 'react-icons/fi';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import axios from '../utils/axios';
import constants from '../utils/constants';
import { setError, setLoadingDialog } from '../store';

export default function Home() {
  const [messageText, setMessageText] = useState('');
  const [backgroundMode, setBackgroundMode] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(false);
  const accessToken = useSelector((state) => state.accessToken);
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const createThread = async () => {
    const task = messageText.trim();
    if (!task) return;

    setMessageText('');
    dispatch(setLoadingDialog(true));
    try {
      const response = await axios.post(
        '/threads',
        {
          task,
          background_mode: backgroundMode,
          extended_thinking_mode: thinkingMode,
        },
        { headers: { Authorization: 'Bearer ' + accessToken } }
      );
      const data = response.data;
      if (data.type === 'desktop_task') {
        const wantsBackground = backgroundMode || data.is_background_mode_requested;
        const wantsThinking = thinkingMode || data.is_extended_thinking_mode_requested;
        if (wantsBackground && !backgroundMode) {
          const ready = await window.electronAPI.isBackgroundModeReady();
          if (!ready) {
            window.electronAPI.startBackgroundSetup();
            return;
          }
        }
        setBackgroundMode(Boolean(wantsBackground));
        setThinkingMode(Boolean(wantsThinking));
        window.electronAPI.setLastThinkingModeValue(String(Boolean(wantsThinking)));
        window.electronAPI.launchAIAgent(
          process.env.REACT_APP_PROTOCOL + '://' + process.env.REACT_APP_DNS,
          data.thread_id,
          wantsBackground
        );
      }
      navigate('/threads/' + data.thread_id);
    } catch (error) {
      const message = error.response?.data?.message === 'Not_Browser_Task_BG_Mode'
        ? 'Background mode is limited to browser tasks.'
        : constants.GENERAL_ERROR;
      dispatch(setError(true, message));
      window.setTimeout(() => dispatch(setError(false, '')), 3500);
    } finally {
      dispatch(setLoadingDialog(false));
    }
  };

  const onBGModeToggleChange = async (value) => {
    if (value) {
      const ready = await window.electronAPI.isBackgroundModeReady();
      if (!ready) {
        window.electronAPI.startBackgroundSetup();
        return;
      }
    }
    setBackgroundMode(value);
  };

  const handleTextEnterKey = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      createThread();
    }
  };

  useEffect(() => {
    const loadPreferences = async () => {
      const background = await window.electronAPI.getLastBackgroundModeValue();
      const thinking = await window.electronAPI.getLastThinkingModeValue();
      setBackgroundMode(background === 'true');
      setThinkingMode(thinking === 'true');
    };
    loadPreferences();
  }, []);

  useEffect(() => {
    if (window.electronAPI?.onAIAgentLaunch) {
      window.electronAPI.onAIAgentLaunch((threadId) => navigate('/threads/' + threadId));
    }
  }, [navigate]);

  return (
    <main className="tasker-home">
      <section className="tasker-hero">
        <div className="tasker-kicker"><FiActivity aria-hidden="true" /> Tasker command center</div>
        <h1>Put the desktop<br /><span>in motion.</span></h1>
        <p className="tasker-hero-copy">
          Describe the outcome. Tasker plans the work, operates the visible desktop,
          and verifies the handoff as it moves.
        </p>

        <div className="tasker-system-strip" aria-label="Tasker execution status">
          <div><span className="tasker-status-dot" aria-hidden="true" /><strong>Ready</strong><small>Desktop connected</small></div>
          <div><FiLayers aria-hidden="true" /><strong>Dual-lobe</strong><small>A executes · B prepares</small></div>
          <div><FiMonitor aria-hidden="true" /><strong>Screen-aware</strong><small>Boundary verification on</small></div>
        </div>
      </section>

      <form className="tasker-compose-card" onSubmit={(event) => { event.preventDefault(); createThread(); }}>
        <div className="tasker-compose-heading">
          <div>
            <label htmlFor="tasker-command">What should happen?</label>
            <p>Use plain language. You can describe a multi-step outcome.</p>
          </div>
          <span className="tasker-command-hint">Enter to run · Shift + Enter for a new line</span>
        </div>
        <textarea
          id="tasker-command"
          className="tasker-command-input"
          placeholder="Open Chrome, find the latest project brief, and save a copy on my desktop..."
          rows={4}
          value={messageText}
          onChange={(event) => setMessageText(event.target.value)}
          onKeyDown={handleTextEnterKey}
          aria-describedby="tasker-command-help"
        />
        <div className="tasker-compose-actions">
          <div className="tasker-option-group" role="group" aria-label="Execution options">
            <button type="button" className={'tasker-option' + (backgroundMode ? ' is-selected' : '')} onClick={() => onBGModeToggleChange(!backgroundMode)}>
              <FiMoon aria-hidden="true" /><span>Background</span>
            </button>
            <button type="button" className={'tasker-option' + (thinkingMode ? ' is-selected' : '')} onClick={() => setThinkingMode(!thinkingMode)}>
              <FiZap aria-hidden="true" /><span>Extended reasoning</span>
            </button>
          </div>
          <button className="tasker-submit" type="submit" disabled={!messageText.trim()}>
            <span>Run task</span><FiArrowUpRight aria-hidden="true" />
          </button>
        </div>
        <p id="tasker-command-help" className="tasker-compose-note">
          Tasker will ask the model for actions only after it has the current desktop context.
        </p>
      </form>

      <section className="tasker-runbook" aria-label="How Tasker works">
        <div className="tasker-section-label">The operating model</div>
        <div className="tasker-runbook-grid">
          <article><span>01</span><h2>Intent</h2><p>Your request becomes a focused desktop task.</p></article>
          <article><span>02</span><h2>Motion</h2><p>Lobe A executes action batches while B prepares the next boundary.</p></article>
          <article><span>03</span><h2>Proof</h2><p>The screen observer checks the transition before handoff.</p></article>
        </div>
      </section>
    </main>
  );
}
