import React, { useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { FiActivity, FiClock, FiPlus, FiTerminal } from 'react-icons/fi';
import { useSelector } from 'react-redux';
import axios from '../utils/axios';
import constants from '../utils/constants';
import { subscribeHandsStatus } from '../state/handsBus';

export default function TaskerSidebar() {
  const [threads, setThreads] = useState([]);
  const [liveRun, setLiveRun] = useState(null);
  const accessToken = useSelector((state) => state.accessToken);
  const navigate = useNavigate();

  useEffect(() => subscribeHandsStatus(function (status) {
    // Live execution reflects into the listview titles: the thread entering the
    // pet state gets its status line pinned next to its title.
    setLiveRun(status && status.mode === 'pet' ? status : null);
  }), []);

  useEffect(() => {
    let mounted = true;
    axios.get('/threads', {
      headers: { Authorization: 'Bearer ' + accessToken },
    }).then((response) => {
      if (mounted) setThreads(response.data || []);
    }).catch((error) => {
      if (error.response?.status === constants.status.UNAUTHORIZED) {
        window.location.reload();
      }
    });
    return () => { mounted = false; };
  }, [accessToken]);

  return (
    <aside className="tasker-sidebar" aria-label="Hands workspace">
      <button className="tasker-brand" onClick={() => navigate('/')} aria-label="Open Hands home">
        <span className="tasker-mark" aria-hidden="true">H</span>
        <span>
          <strong>Hands</strong>
          <small>desktop control</small>
        </span>
      </button>

      <button className="tasker-new-task" onClick={() => navigate('/')}>
        <FiPlus aria-hidden="true" />
        <span>New task</span>
        <kbd>⌘K</kbd>
      </button>

      <div className="tasker-sidebar-label">Workspace</div>
      <nav className="tasker-thread-list" aria-label="Task history">
        {threads.length === 0 ? (
          <div className="tasker-empty-sidebar">
            <FiClock aria-hidden="true" />
            <span>Your task history will appear here.</span>
          </div>
        ) : (
          threads.map((thread) => (
            <NavLink
              key={'task-' + thread.id}
              to={'/threads/' + thread.id}
              className={({ isActive }) => 'tasker-thread-link' + (isActive ? ' is-active' : '')}
            >
              <FiTerminal aria-hidden="true" />
              <span>
                {thread.title}
                {liveRun && liveRun.threadId === thread.id && (
                  <em className="hands-live-tag" title={liveRun.statusLine || ''}>
                    {liveRun.activeLanes > 1 ? liveRun.activeLanes + ' lanes' : 'live'}
                  </em>
                )}
                {liveRun && !liveRun.threadId && thread.status === 'working' && (
                  <em className="hands-live-tag">{liveRun.statusLine || 'running'}</em>
                )}
              </span>
            </NavLink>
          ))
        )}
      </nav>

      <div className="tasker-sidebar-footer">
        <div className="tasker-engine-status">
          <span className="tasker-status-dot" aria-hidden="true" />
          <span>Engine ready</span>
        </div>
        <div className="tasker-engine-meta">
          <FiActivity aria-hidden="true" />
          <span>Dual-lobe control</span>
        </div>
      </div>
    </aside>
  );
}
