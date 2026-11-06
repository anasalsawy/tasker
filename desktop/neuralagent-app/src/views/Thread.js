import React, { useEffect, useRef, useState } from 'react';
import { FiEdit3, FiRadio, FiSend, FiTrash2, FiX, FiZap } from 'react-icons/fi';
import { useNavigate, useParams } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import axios from '../utils/axios';
import constants from '../utils/constants';
import { setError, setLoadingDialog } from '../store';
import TaskerMessage from '../components/TaskerMessage';
import ExecutionPet from '../components/ExecutionPet';
import useHands from '../hooks/useHands';
import { publishHandsStatus } from '../state/handsBus';

const PERSONA_BASE = constants.SERVER_URL + '/aiagent/persona';

export default function Thread() {
  const [thread, setThread] = useState(null);
  const [messages, setMessages] = useState([]);
  const [messageText, setMessageText] = useState('');
  const [thinkingMode, setThinkingMode] = useState(false);
  const [liveEvents, setLiveEvents] = useState([]);
  const accessToken = useSelector((state) => state.accessToken);
  const { tid } = useParams();
  const bottomRef = useRef(null);
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const hands = useHands({ personaBaseUrl: PERSONA_BASE, accessToken: accessToken });

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
    if (!text) return;

    setMessageText('');

    // Persona path: local echo + optimistic SSE streaming. Task recognition
    // (bar→pet) is done POST-HOC by the reducer from tool/lane events.
    hands.dispatch({ kind: 'user_text', text });
    hands.streamAct(tid, { text });

    // Fire-and-forget: mirror the message + classification into the thread
    // store so context builds up. Not awaited — never blocks the reply path.
    axios.post('/threads/' + tid + '/send_message',
      { text, extended_thinking_mode: thinkingMode },
      { headers: { Authorization: 'Bearer ' + accessToken } }
    ).then((response) => {
      const data = response.data;
      getThread();
      getThreadMessages();
      if (data.type === 'desktop_task') hands.dispatch({ kind: 'task_recognized', title: text });
    }).catch(() => {});
  };

  const cancelRunningTask = async () => {
    if (thread?.status !== 'working') return;
    dispatch(setLoadingDialog(true));
    try {
      await axios.post('/threads/' + tid + '/cancel_task', {}, {
        headers: { Authorization: 'Bearer ' + accessToken },
      });
      if (window.electronAPI?.stopAIAgent) window.electronAPI.stopAIAgent();
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
  }, [messages, liveEvents]);

  useEffect(() => {
    if (!window.electronAPI?.onAIAgentStatus) return undefined;
    const unsubscribe = window.electronAPI.onAIAgentStatus((event) => {
      setLiveEvents((previous) => [...previous, event].slice(-30));
    });
    return unsubscribe;
  }, [tid]);

  // Feed the collapsed surfaces + sidebar titles from this page too.
  useEffect(() => {
    publishHandsStatus({
      threadId: tid,
      threadTitle: thread?.title,
      mode: hands.state.mode,
      statusLine: hands.selectors.statusLine,
      activeLanes: hands.selectors.activeLanes,
      online: Boolean(accessToken),
    });
  }, [tid, thread?.title, hands.state]);

  useEffect(() => {
    const loadPreferences = async () => {
      if (!window.electronAPI?.getLastThinkingModeValue) return;
      const thinking = await window.electronAPI.getLastThinkingModeValue();
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
          <h1>{thread.title}</h1>
        </div>
        <div className="tasker-thread-header-actions">
          {hands.state.mode === 'pet' && <ExecutionPet state={hands.state} onStop={cancelRunningTask} call={hands.call} />}
          <span className={'tasker-run-status ' + (isWorking ? 'is-working' : '')}>
            <span className="tasker-status-dot" aria-hidden="true" />
            {isWorking ? 'Executing' : 'Standby'}
          </span>
          {isWorking && (
            <button className="tasker-stop-button" onClick={cancelRunningTask}>
              <FiX aria-hidden="true" /> Stop
            </button>
          )}
          <button className="tasker-icon-button" onClick={deleteThread} aria-label="Delete task history" title="Delete task history">
            <FiTrash2 aria-hidden="true" />
          </button>
        </div>
      </header>

      <section className="tasker-log-panel" aria-label="Task timeline">
        <div className="tasker-panel-header">
          <span className="tasker-live-label"><FiRadio aria-hidden="true" /> Live</span>
        </div>
        <div className="tasker-message-list">
          {messages.length === 0 ? (
            <div className="tasker-empty-log">The task timeline will appear as the engine works.</div>
          ) : (
            messages.map((message) => <TaskerMessage key={'message-' + message.id} message={message} />)
          )}
          {liveEvents.map((event, index) => (
            <div
              className={'tasker-working-line tasker-live-event ' + (event.level === 'error' ? 'is-error' : '')}
              key={(event.timestamp || index) + '-' + index}
            >
              <span className="tasker-working-pulse" aria-hidden="true" />
              <span>{event.message}</span>
            </div>
          ))}
          {isWorking && liveEvents.length === 0 && (
            <div className="tasker-working-line">
              <span className="tasker-working-pulse" aria-hidden="true" />
              <span>Starting execution…</span>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </section>

      <form className="tasker-thread-composer" onSubmit={(event) => { event.preventDefault(); sendMessage(); }}>
        <div className="tasker-thread-compose-row">
          <textarea
            id="tasker-follow-up"
            value={messageText}
            rows={1}
            placeholder="Follow up…"
            onChange={(event) => setMessageText(event.target.value)}
            onKeyDown={handleTextEnterKey}
          />
          <button className="tasker-submit tasker-submit-compact" type="submit" disabled={!messageText.trim()} aria-label="Send follow-up">
            <FiSend aria-hidden="true" />
          </button>
        </div>
        <div className="tasker-compose-controls">
          <button type="button" className="tasker-control-chip" onClick={() => setThinkingMode(!thinkingMode)}>
            <FiZap aria-hidden="true" /> Thinking {thinkingMode ? 'on' : 'off'}
          </button>
          <span className="tasker-compose-note"><FiEdit3 aria-hidden="true" /> Enter sends</span>
        </div>
      </form>
    </main>
  );
}
