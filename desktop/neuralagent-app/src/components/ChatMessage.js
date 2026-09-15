import React from 'react';
import styled from 'styled-components';
import { Tag } from './Elements/Tag';

import {
  FaMousePointer,
  FaRegKeyboard,
  FaCheckCircle,
  FaScroll,
  FaPause
} from 'react-icons/fa';
import {
  MdOutlineOpenInBrowser,
  MdDragIndicator,
  MdCancel,
  MdError,
  MdApps,
  MdScreenShare
} from 'react-icons/md';
import { FiCornerDownRight } from 'react-icons/fi';
import { GiBrain } from 'react-icons/gi';

const MessageContainer = styled.div`
  display: flex;
  justify-content: ${({ role }) => (role === 'user' ? 'flex-end' : 'flex-start')};
  padding: 10px 18px;
`;

const Bubble = styled.div`
  background-color: ${({ role }) =>
    role === 'user' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(255, 255, 255, 0.05)'};
  color: #fff;
  padding: 14px 18px;
  border-radius: 16px;
  max-width: 65%;
  box-shadow: 0 1px 4px rgba(0,0,0,0.35);
  font-size: 14.5px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  border-bottom-left-radius: ${({ role }) => (role === 'user' ? '16px' : '0')};
  border-bottom-right-radius: ${({ role }) => (role === 'user' ? '0' : '16px')};
`;

const ThoughtBox = styled.div`
  font-style: italic;
  opacity: 0.9;
  padding: 10px;
  background-color: #2a2a2a;
  border-left: 3px solid #4ade80;
  border-radius: 6px;
  margin-top: 6px;
  font-size: 13px;
`;

const Label = styled.div`
  font-size: 13px;
  color: #ccc;
  margin-top: 8px;
`;

const Spacer = styled.div`
  height: 6px;
`;

const iconStyle = { color: '#fff', fontSize: '15px' };

const actionMap = {
  mouse_move: { label: 'Move Cursor', color: 'var(--primary-color)', icon: <FaMousePointer style={iconStyle} /> },
  left_click: { label: 'Click', color: 'var(--primary-color)', icon: <FaMousePointer style={iconStyle} /> },
  right_click: { label: 'Right Click', color: 'var(--primary-color)', icon: <FaMousePointer style={iconStyle} /> },
  double_click: { label: 'Double Click', color: 'var(--primary-color)', icon: <FaMousePointer style={iconStyle} /> },
  triple_click: { label: 'Triple Click', color: 'var(--primary-color)', icon: <FaMousePointer style={iconStyle} /> },
  left_click_drag: { label: 'Click & Drag', color: 'var(--primary-color)', icon: <MdDragIndicator style={iconStyle} /> },
  left_mouse_down: { label: 'Mouse Down', color: 'var(--primary-color)', icon: <MdDragIndicator style={iconStyle} /> },
  left_mouse_up: { label: 'Mouse Up', color: 'var(--primary-color)', icon: <MdDragIndicator style={iconStyle} /> },
  scroll: { label: 'Scroll', color: 'var(--primary-color)', icon: <FaScroll style={iconStyle} /> },
  type: { label: 'Type Text', color: 'var(--primary-color)', icon: <FaRegKeyboard style={iconStyle} /> },
  key: { label: 'Press Key', color: 'var(--primary-color)', icon: <FaRegKeyboard style={iconStyle} /> },
  hold_key: { label: 'Hold Key', color: 'var(--primary-color)', icon: <FaRegKeyboard style={iconStyle} /> },
  key_combo: { label: 'Key Combo', color: 'var(--primary-color)', icon: <FaRegKeyboard style={iconStyle} /> },
  wait: { label: 'Wait', color: 'var(--primary-color)', icon: <FaPause style={iconStyle} /> },
  launch_browser: { label: 'Launch Browser', color: 'var(--primary-color)', icon: <MdOutlineOpenInBrowser style={iconStyle} /> },
  launch_app: { label: 'Launch App', color: 'var(--primary-color)', icon: <MdApps style={iconStyle} /> },
  focus_app: { label: 'Switch To App', color: 'var(--primary-color)', icon: <MdApps style={iconStyle} /> },
  request_screenshot: { label: 'Request Screenshot', color: 'var(--primary-color)', icon: <MdScreenShare style={iconStyle} /> },
  tool_use: { label: 'Tool Use', color: 'var(--primary-color)', icon: <FaRegKeyboard style={iconStyle} /> },
  subtask_completed: { label: 'Step Completed', color: 'var(--primary-color)', icon: <FaCheckCircle style={iconStyle} /> },
  subtask_failed: { label: 'Step Failed', color: 'var(--danger-color)', icon: <MdError style={iconStyle} /> },
  task_completed: { label: 'Task Completed', color: 'var(--success-color)', icon: <FaCheckCircle style={iconStyle} /> },
  task_canceled: { label: 'Task Canceled', color: 'var(--danger-color)', icon: <MdCancel style={iconStyle} /> },
  task_failed: { label: 'Task Failed', color: 'var(--danger-color)', icon: <MdError style={iconStyle} /> }
};


export default function ChatMessage({ message }) {
  const isUser = message.thread_chat_from !== 'from_ai';
  const role = isUser ? 'user' : 'assistant';

  const getContent = () => {
    const type = message.thread_chat_type;
    const raw = message.text;

    if (type === 'normal_message') return <>{raw}</>;

    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return '[Failed to parse message]';
    }

    if (type === 'classification') {
      const isDesktop = parsed.type === 'desktop_task';
      return (
        <>
          <Tag>
            {isDesktop ? <MdOutlineOpenInBrowser style={iconStyle} /> : <FiCornerDownRight style={iconStyle} />}
            {isDesktop ? 'Desktop Task' : 'Inquiry'}
          </Tag>
          <Spacer />
          <div>{parsed.response}</div>
        </>
      );
    }

    if (type === 'action') {
      const actionMeta = actionMap[parsed.action] || {
        label: parsed.action,
        icon: <FaMousePointer style={iconStyle} />
      };

      return (
        <>
          <Tag color={actionMeta.color}>
            {actionMeta.icon}
            {actionMeta.label}
          </Tag>

          {parsed.action === 'tool_use' && (
            <>
              {parsed.tool && <><Label>Tool:</Label> {parsed.tool}</>}
              {parsed.args && (
                <>
                  <Label>Arguments:</Label> {JSON.stringify(parsed.args)}
                </>
              )}
            </>
          )}

          {parsed.text && <><Label>Text:</Label> {parsed.text}</>}
          {parsed.url && <><Label>URL:</Label> {parsed.url}</>}
          {parsed.app_name && <><Label>App Name:</Label> {parsed.app_name}</>}
          {parsed.coordinate && (
            <>
              <Label>Coordinate:</Label> ({parsed.coordinate.x}, {parsed.coordinate.y})
            </>
          )}
          {parsed.from && parsed.to && (
            <>
              <Label>Drag:</Label> From ({parsed.from.x}, {parsed.from.y}) → ({parsed.to.x}, {parsed.to.y})
            </>
          )}
          {parsed.duration && <><Label>Duration:</Label> {parsed.duration}s</>}
          {parsed.reasoning && <ThoughtBox>{parsed.reasoning}</ThoughtBox>}
        </>
      );
    }

    if (type === 'browser_use' || type === 'bg_mode_browser') {
      return (
        <>
          <Tag><MdOutlineOpenInBrowser style={iconStyle} />Using The Browser</Tag>
          <Spacer />
    
          {parsed.current_state && (
            <div style={{ marginBottom: '10px' }}>
              <strong>Evaluation:</strong> {parsed.current_state.evaluation_previous_goal}<br />
              <strong>Memory:</strong> {parsed.current_state.memory}<br />
              <strong>Next Goal:</strong> {parsed.current_state.next_goal}
            </div>
          )}
    
          {parsed.action && Array.isArray(parsed.action) && parsed.action.length > 0 && (
            <div>
              <strong>Next Actions:</strong>
              <ol style={{ marginTop: '8px', paddingLeft: '20px' }}>
                {parsed.action.map((act, idx) => {
                  const actionType = Object.keys(act)[0];
                  const params = act[actionType];
    
                  return (
                    <li key={idx} style={{ marginBottom: '8px' }}>
                      <strong>Action:</strong> {actionType}<br />
                      {params && Object.keys(params).map((key) => (
                        <div key={key}>
                          <strong>{key}:</strong> {typeof params[key] === 'object' ? JSON.stringify(params[key]) : params[key]}
                        </div>
                      ))}
                    </li>
                  );
                })}
              </ol>
            </div>
          )}
        </>
      );
    }

    if (type === 'desktop_use') {
      return (
        <>
          <Tag><MdApps style={iconStyle} />Using The Desktop</Tag>
          <Spacer />
    
          {parsed.current_state && (
            <div style={{ marginBottom: '10px' }}>
              <strong>Evaluation:</strong> {parsed.current_state.current_evaluation}<br />
              <strong>Memory:</strong> {parsed.current_state.memory}<br />
              <strong>Next Goal:</strong> {parsed.current_state.next_steps}
            </div>
          )}
    
          {parsed.action && (
            <div>
              <strong>Next Action:</strong><br />
              <Tag color={actionMap[parsed.action]?.color || 'var(--primary-color)'}>
                {actionMap[parsed.action]?.icon || <FaMousePointer style={iconStyle} />}
                {actionMap[parsed.action]?.label || parsed.action}
              </Tag>
    
              <div style={{ marginTop: '6px' }}>
                {Object.entries(parsed)
                  .filter(([key]) => key !== 'action' && key !== 'current_state')
                  .map(([key, value]) => (
                    <div key={key}><strong>{key}:</strong> {typeof value === 'object' ? JSON.stringify(value) : value}</div>
                  ))}
              </div>
            </div>
          )}
        </>
      );
    }

    if (type === 'desktop_use_v2' || type === 'bg_mode_browser_v2') {
      return (
        <>
          {
            type === 'desktop_use_v2' ? <Tag><MdApps style={iconStyle} />Using The Desktop</Tag> : <Tag><MdOutlineOpenInBrowser style={iconStyle} />Using The Background Browser</Tag>
          }
          <Spacer />

          {parsed.current_state && (
            <div style={{ marginBottom: '10px' }}>
              <strong>Evaluation:</strong> {parsed.current_state.evaluation_previous_goal}<br />
              <strong>Memory:</strong> {parsed.current_state.memory}<br />
              <strong>Next Goal:</strong> {parsed.current_state.next_goal}
            </div>
          )}

          {parsed.actions && parsed.actions.length > 0 && (
            <div>
              <strong>Next Actions:</strong>
              <ol style={{ marginTop: '8px', paddingLeft: '20px' }}>
                {parsed.actions.map((actionObj, idx) => (
                  <li key={idx} style={{ marginBottom: '8px' }}>
                    <Tag color={actionMap[actionObj.action]?.color || 'var(--primary-color)'}>
                      {actionMap[actionObj.action]?.icon || <FaMousePointer style={iconStyle} />}
                      {actionMap[actionObj.action]?.label || actionObj.action}
                    </Tag>
                    {actionObj.params && Object.entries(actionObj.params).map(([key, value]) => (
                      <div key={key}><strong>{key}:</strong> {typeof value === 'object' ? JSON.stringify(value) : value}</div>
                    ))}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </>
      );
    }

    if (type === 'plan') {
      return (
        <>
          <Tag><FiCornerDownRight style={iconStyle} />Plan</Tag>
          <Spacer />
          {parsed.subtasks?.length > 0 ? (
            <ol style={{ margin: 0, paddingLeft: 20 }}>
              {parsed.subtasks.map((step, idx) => (
                <li key={idx}>
                  <div><strong>Step:</strong> {step.subtask}</div>
                  <div><strong>Type:</strong> {step.type === 'browser_subtask' ? 'Browser' : 'Desktop'}</div>
                </li>
              ))}
            </ol>
          ) : (
            <div>[Empty plan]</div>
          )}
        </>
      );
    }

    if (type === 'thinking' && message.chain_of_thought) {
      return (
        <>
          <Tag><GiBrain style={iconStyle} />Thinking</Tag>
          <Spacer />
          <ThoughtBox>{message.chain_of_thought}</ThoughtBox>
        </>
      );
    }

    return '[Unknown message type]';
  };

  return (
    <MessageContainer role={role}>
      <Bubble role={role}>
        {getContent()}
      </Bubble>
    </MessageContainer>
  );
}
