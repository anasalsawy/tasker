import React from 'react';
import { FiCheck, FiCpu, FiEdit3, FiExternalLink, FiMousePointer, FiPlay, FiTerminal, FiX } from 'react-icons/fi';

function actionLabel(action) {
  const labels = {
    left_click: 'Click',
    double_click: 'Double click',
    right_click: 'Right click',
    mouse_move: 'Move cursor',
    left_click_drag: 'Drag',
    type: 'Type',
    key: 'Press key',
    key_combo: 'Key combination',
    hold_key: 'Hold key',
    scroll: 'Scroll',
    wait: 'Wait',
    launch_browser: 'Open browser',
    launch_app: 'Launch app',
    focus_app: 'Focus app',
    request_screenshot: 'Read screen',
    subtask_completed: 'Step completed',
    subtask_failed: 'Step failed',
    task_completed: 'Task completed',
    task_failed: 'Task failed',
    task_canceled: 'Task canceled',
    tool_use: 'Tool call',
  };
  return labels[action] || action || 'Action';
}

function actionIcon(action) {
  if (action === 'subtask_completed' || action === 'task_completed') return <FiCheck aria-hidden="true" />;
  if (action === 'subtask_failed' || action === 'task_failed' || action === 'task_canceled') return <FiX aria-hidden="true" />;
  if (action === 'launch_browser') return <FiExternalLink aria-hidden="true" />;
  if (['type', 'key', 'key_combo', 'hold_key'].includes(action)) return <FiEdit3 aria-hidden="true" />;
  if (['left_click', 'double_click', 'right_click', 'mouse_move'].includes(action)) return <FiMousePointer aria-hidden="true" />;
  return <FiPlay aria-hidden="true" />;
}

function ActionRow({ action }) {
  const kind = action?.action || action?.type;
  const params = action?.params || action?.parameters || {};
  const details = [];
  if (params.app_name) details.push(params.app_name);
  if (params.url) details.push(params.url);
  if (params.text) details.push(params.text);
  if (params.keys) details.push(Array.isArray(params.keys) ? params.keys.join(' + ') : params.keys);
  if (params.duration) details.push(params.duration + 's');

  return (
    <div className={'tasker-action-row action-' + kind}>
      <span className="tasker-action-icon">{actionIcon(kind)}</span>
      <span className="tasker-action-label">{actionLabel(kind)}</span>
      {details.length > 0 && <span className="tasker-action-detail">{details.join(' · ')}</span>}
    </div>
  );
}

export default function TaskerMessage({ message }) {
  const isUser = message.thread_chat_from !== 'from_ai';
  const raw = message.text || '';
  let parsed = null;
  if (!isUser) {
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = null;
    }
  }

  let content = isUser ? (
    <p className="tasker-message-text">{raw}</p>
  ) : (
    <p className="tasker-message-text">{raw || 'No readable output.'}</p>
  );

  if (!isUser && message.thread_chat_type === 'classification' && parsed) {
    content = (
      <>
        <div className="tasker-message-badge"><FiCpu aria-hidden="true" /> Intent classified</div>
        <p className="tasker-message-text">{parsed.response || 'Task received.'}</p>
      </>
    );
  } else if (!isUser && message.thread_chat_type === 'plan' && parsed) {
    content = (
      <>
        <div className="tasker-message-badge"><FiTerminal aria-hidden="true" /> Plan</div>
        <ol className="tasker-plan-list">
          {(parsed.subtasks || []).map((step, index) => (
            <li key={index}><span>{index + 1}</span>{step.subtask}</li>
          ))}
        </ol>
      </>
    );
  } else if (!isUser && message.thread_chat_type === 'thinking' && message.chain_of_thought) {
    content = (
      <>
        <div className="tasker-message-badge"><FiCpu aria-hidden="true" /> Internal reasoning</div>
        <p className="tasker-message-text tasker-muted-text">{message.chain_of_thought}</p>
      </>
    );
  } else if (!isUser && parsed && (message.thread_chat_type === 'desktop_use' || parsed.actions)) {
    content = (
      <>
        <div className="tasker-message-badge"><FiPlay aria-hidden="true" /> Execution batch</div>
        {parsed.current_state?.next_goal && (
          <p className="tasker-message-context">{parsed.current_state.next_goal}</p>
        )}
        <div className="tasker-action-list">
          {(parsed.actions || []).map((action, index) => <ActionRow key={index} action={action} />)}
        </div>
      </>
    );
  }

  return (
    <article className={'tasker-message ' + (isUser ? 'from-user' : 'from-engine')}>
      <div className="tasker-message-rail" aria-hidden="true" />
      <div className="tasker-message-body">
        <div className="tasker-message-meta">
          <span>{isUser ? 'You' : 'Tasker engine'}</span>
          <time>{message.created_at ? new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}</time>
        </div>
        {content}
      </div>
    </article>
  );
}
