import React, { useEffect, useRef, useState } from 'react';
import { FiActivity, FiEdit3, FiMoon, FiRadio, FiSend, FiTrash2, FiX, FiZap } from 'react-icons/fi';
import { useNavigate, useParams } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import axios from '../utils/axios';
import constants from '../utils/constants';
import { setError, setLoadingDialog } from '../store';
import TaskerMessage from '../components/TaskerMessage';

export default function Thread() {
  const [thread, setThread] = useState(null);
  const [messages, setMessages] = useState([]);
  const [messageText, setMessageText] = useState('');
  const [isSendingMessage, setSendingMessage] = useState(false);
  const [backgroundMode, setBackgroundMode] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(false);
  const accessToken = useSelector((state) => state.accessToken);
  const { tid } = useParams();
  const bottomRef = useRef(null);
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const getThread = async () => {
    try {
      const response = await axios.get('/threads/' + tid, {
        headers: { Authorization: 'Bearer ' + accessToken },
      });
      setThread(response.data);
    } catch (error) {
      if (error.response?.status === constants.status.UNAUTHORIZED) window.location.reload();
    }
  };

  const getThreadMessages = async () => {
    try {
      const response = await axios.get('/threads/' + tid + '/thread_messages', {
        headers: { Authorization: 'Bearer ' + accessToken },
      });
      setMessages(response.data || []);
    } catch (error) {
      if (error.response?.status === constants.status.UNAUTHORIZED) window.location.reload();
    }
  };

  const showError = (message) => {
    dispatch(setError(true, message));
    window.setTimeout(() => dispatch(setError(false, '')), 3500);
  };

  const sendMessage = async () => {
    const text = messageText.trim();
    if (!text || isSendingMessage || thread?.status === 'working') return;

    setMessageText('');
    setSendingMessage(true);
    dispatch(setLoadingDialog(true));
    try {
      const response = await axios.post(
        '/threads/' + tid + '/send_message',
        { text, background_mode: backgroundMode, extended_thinking_mode: thinkingMode },
        { headers: { Authorization: 'Bearer ' + accessToken } }
      );
      const data = response.data;
      if (data.type === 'desktop_task') {
        const wantsBackground = backgroundMode || data.is_background_mode_requested;
        const wantsThinking = thinkingMode || data.is_extended_thinking_mode_requested;
        if (wantsBackground && !backgroundMode) {
          const ready = await window.electronAPI.isBackgroundModeReady();
          if (!ready) {
            await axios.post('/threads/' + tid + '/cancel_task', {}, {
              headers: { Authorization: 'Bearer ' + accessToken },
            });
            window.electronAPI.startBackgroundSetup();
            return;
          }
        }
        setBackgroundMode(Boolean(wantsBackground));
        setThinkingMode(Boolean(wantsThinking));
        window.electronAPI.setLastThinkingModeValue(String(Boolean(wantsThinking)));
        window.electronAPI.launchAIAgent(
          process.env.REACT_APP_PROTOCOL + '://' + process.env.REACT_APP_DNS,
          tid,
          wantsBackground
        );
      }
      await getThread();
      await getThreadMessages();
    } catch (error) {
      if (error.response?.data?.message === 'Not_Browser_Task_BG_Mode') {
        showError('Background mode is limited to browser tasks.');
      } else {
        showError(constants.GENERAL_ERROR);
      }
    } finally {
      setSendingMessage(false);
      dispatch(setLoadingDialog(false));
    }
  };

  const cancelRunningTask = async () => {
    if (thread?.status !== 'working') return;
    dispatch(setLoadingDialog(true));
    try {
      await axios.post('/threads/' + tid + '/cancel_task', {}, {
        headers: { Authorization: 'Bearer ' + accessToken },
      });
      window.electronAPI.stopAIAgent();
      await getThread();
      await getThreadMessages();
    } catch {
      showError(constants.GENERAL_ERROR);
    } finally {
      dispatch(setLoadingDialog(false));
    }
  };

  const deleteThread = async () => {
    if (!window.confirm('Delete this task history?')) return;
    dispatch(setLoadingDialog(true));
    try {
      await axios.delete('/threads/' + tid, {
        headers: { Authorization: 'Bearer ' + accessToken },
      });
      navigate('/');
    } catch {
      showError(constants.GENERAL_ERROR);
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
      sendMessage();
    }
  };

  useEffect(() => {
    getThread();
    getThreadMessages();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const loadPreferences = async () => {
      const background = await window.electronAPI.getLastBackgroundModeValue();
      const thinking = await window.electronAPI.getLastThinkingModeValue();
      setBackgroundMode(background === 'true');
      setThinkingMode(thinking === 'true');
    };
    loadPreferences();

    if (window.electronAPI?.onAIAgentExit) {
      window.electronAPI.onAIAgentExit(() => {
        getThread();
        getThreadMessages();
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  if (!thread) return <main className="tasker-loading-view">Loading task...</main>;

  const isWorking = thread.status === 'working';

  return (
    <main className="tasker-thread">
      <header className="tasker-thread-header">
        <div>
          <div className="tasker-kicker"><FiActivity aria-hidden="true" /> Task run</div>
          <h1>{thread.title}</h1>
        </div>
        <div className="tasker-thread-header-actions">
          <span className={'tasker-run-status ' + (isWorking ? 'is-working' : '')}>
            <span className="tasker-status-dot" aria-hidden="true" />
            {isWorking ? 'Executing' : 'Standby'}
          </span>
          <button className="tasker-icon-button" onClick={deleteThread} aria-label="Delete task history" title="Delete task history">
            <FiTrash2 aria-hidden="true" />
          </button>
        </div>
      </header>

      <div className="tasker-thread-grid">
        <section className="tasker-log-panel" aria-label="Task timeline">
          <div className="tasker-panel-header">
            <div>
              <span className="tasker-panel-eyebrow">Run timeline</span>
              <h2>What Tasker is doing</h2>
            </div>
            <span className="tasker-live-label"><FiRadio aria-hidden="true" /> Live log</span>
          </div>
          <div className="tasker-message-list">
            {messages.length === 0 ? (
              <div className="tasker-empty-log">The task timeline will appear as the engine works.</div>
            ) : (
              messages.map((message) => <TaskerMessage key={'message-' + message.id} message={message} />)
            )}
            {isWorking && (
              <div className="tasker-working-line">
                <span className="tasker-working-pulse" aria-hidden="true" />
                <span>Watching the desktop and preparing the next boundary…</span>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </section>

        <aside className="tasker-inspector" aria-label="Task run details">
          <div className="tasker-inspector-card">
            <span className="tasker-panel-eyebrow">Execution profile</span>
            <div className="tasker-profile-name">Screen-aware</div>
            <p>A executes the current batch. B prepares the next one while the screen observer checks the handoff.</p>
            <div className="tasker-inspector-row"><span>Provider state</span><strong>{isWorking ? 'Connected' : 'Idle'}</strong></div>
            <div className="tasker-inspector-row"><span>Verification</span><strong>Boundary check</strong></div>
          </div>

          <div className="tasker-inspector-card">
            <span className="tasker-panel-eyebrow">Run controls</span>
            <button className="tasker-control-button" onClick={() => setThinkingMode(!thinkingMode)}>
              <FiZap aria-hidden="true" /><span>Extended reasoning</span><b>{thinkingMode ? 'On' : 'Off'}</b>
            </button>
            <button className="tasker-control-button" onClick={() => onBGModeToggleChange(!backgroundMode)}>
              <FiMoon aria-hidden="true" /><span>Background mode</span><b>{backgroundMode ? 'On' : 'Off'}</b>
            </button>
            {isWorking && (
              <button className="tasker-stop-button" onClick={cancelRunningTask}>
                <FiX aria-hidden="true" /> Stop execution
              </button>
            )}
          </div>
        </aside>
      </div>

      <form className="tasker-thread-composer" onSubmit={(event) => { event.preventDefault(); sendMessage(); }}>
        <label htmlFor="tasker-follow-up">Continue this task</label>
        <div className="tasker-thread-compose-row">
          <textarea
            id="tasker-follow-up"
            value={messageText}
            rows={2}
            placeholder={isWorking ? 'Tasker is executing. Stop it before sending a follow-up.' : 'Add a follow-up instruction…'}
            disabled={isWorking || isSendingMessage}
            onChange={(event) => setMessageText(event.target.value)}
            onKeyDown={handleTextEnterKey}
          />
          <button className="tasker-submit tasker-submit-compact" type="submit" disabled={!messageText.trim() || isWorking || isSendingMessage} aria-label="Send follow-up">
            <FiSend aria-hidden="true" />
          </button>
        </div>
        <div className="tasker-compose-note"><FiEdit3 aria-hidden="true" /> Enter sends · Shift + Enter adds a line</div>
      </form>
    </main>
  );
}
