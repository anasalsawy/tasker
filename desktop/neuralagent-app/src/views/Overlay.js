import React, { useEffect, useState } from 'react';
import { FiActivity, FiMoon, FiSend, FiSquare, FiZap } from 'react-icons/fi';
import { useSelector } from 'react-redux';
import axios from '../utils/axios';
import constants from '../utils/constants';

export default function Overlay() {
  const [expanded, setExpanded] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [messageText, setMessageText] = useState('');
  const [loading, setLoading] = useState(false);
  const [runningThreadId, setRunningThreadId] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [backgroundMode, setBackgroundMode] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(false);
  const accessToken = useSelector((state) => state.accessToken);

  const getSuggestions = async () => {
    try {
      const result = await window.electronAPI.getSuggestions(
        process.env.REACT_APP_PROTOCOL + '://' + process.env.REACT_APP_DNS
      );
      setSuggestions(result.suggestions || []);
    } catch {
      setSuggestions([]);
    }
  };

  const createThread = async (prompt = null) => {
    const task = (prompt || messageText).trim();
    if (!task || loading) return;

    setMessageText('');
    setLoading(true);
    try {
      const response = await axios.post('/threads', {
        task,
        background_mode: backgroundMode,
        extended_thinking_mode: thinkingMode,
      }, {
        headers: { Authorization: 'Bearer ' + accessToken },
      });
      const data = response.data;
      if (data.type === 'desktop_task') {
        const wantsBackground = backgroundMode || data.is_background_mode_requested;
        const wantsThinking = thinkingMode || data.is_extended_thinking_mode_requested;
        setBackgroundMode(Boolean(wantsBackground));
        setThinkingMode(Boolean(wantsThinking));
        window.electronAPI.setLastThinkingModeValue(String(Boolean(wantsThinking)));
        window.electronAPI.launchAIAgent(
          process.env.REACT_APP_PROTOCOL + '://' + process.env.REACT_APP_DNS,
          data.thread_id,
          wantsBackground
        );
        setRunningThreadId(data.thread_id);
      }
    } catch (error) {
      if (error.response?.status === constants.status.UNAUTHORIZED) window.location.reload();
    } finally {
      setLoading(false);
    }
  };

  const cancelRunningTask = async () => {
    if (!runningThreadId) return;
    setLoading(true);
    try {
      await axios.post('/threads/' + runningThreadId + '/cancel_task', {}, {
        headers: { Authorization: 'Bearer ' + accessToken },
      });
      window.electronAPI.stopAIAgent();
      setRunningThreadId(null);
    } finally {
      setLoading(false);
    }
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
  }, []);

  useEffect(() => {
    const loadPreferences = async () => {
      const background = await window.electronAPI.getLastBackgroundModeValue();
      const thinking = await window.electronAPI.getLastThinkingModeValue();
      setBackgroundMode(background === 'true');
      setThinkingMode(thinking === 'true');
    };
    loadPreferences();
  }, []);

  return (
    <div className={'tasker-overlay ' + (expanded ? 'is-expanded' : 'is-compact')}>
      <div className="tasker-overlay-bar">
        <button className="tasker-overlay-brand" onClick={toggleOverlay} aria-label={expanded ? 'Minimize Tasker' : 'Expand Tasker'}>
          <span className="tasker-overlay-mark">T</span>
          {expanded && <span>Tasker</span>}
        </button>
        {expanded && (
          <>
            <input
              className="tasker-overlay-input"
              value={messageText}
              onChange={(event) => setMessageText(event.target.value)}
              placeholder="Describe a task…"
              onKeyDown={(event) => { if (event.key === 'Enter') createThread(); }}
              aria-label="Tasker command"
            />
            {!loading && !runningThreadId && (
              <div className="tasker-overlay-options">
                <button className={'tasker-overlay-option ' + (backgroundMode ? 'is-selected' : '')} onClick={() => onBGModeToggleChange(!backgroundMode)} aria-label="Toggle background mode"><FiMoon /></button>
                <button className={'tasker-overlay-option ' + (thinkingMode ? 'is-selected' : '')} onClick={() => setThinkingMode(!thinkingMode)} aria-label="Toggle extended reasoning"><FiZap /></button>
                <button className="tasker-overlay-send" onClick={() => createThread()} aria-label="Run task"><FiSend /></button>
              </div>
            )}
            {loading && <span className="tasker-overlay-loading" aria-label="Tasker is working"><FiActivity /></span>}
            {runningThreadId && (
              <button className="tasker-overlay-stop" onClick={cancelRunningTask} disabled={loading} aria-label="Stop task"><FiSquare /></button>
            )}
          </>
        )}
      </div>
      {expanded && showSuggestions && (
        <div className="tasker-overlay-suggestions" aria-label="Suggested tasks">
          {suggestions.length === 0 ? (
            <div className="tasker-overlay-empty">Reading the current workspace…</div>
          ) : suggestions.map((suggestion, index) => (
            <button key={index} className="tasker-overlay-suggestion" onClick={() => createThread(suggestion.ai_prompt)}>
              <span>{suggestion.title}</span><FiSend aria-hidden="true" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
