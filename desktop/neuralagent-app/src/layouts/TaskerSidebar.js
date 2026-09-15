import React, { useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { FiActivity, FiClock, FiPlus, FiTerminal } from 'react-icons/fi';
import { useSelector } from 'react-redux';
import axios from '../utils/axios';
import constants from '../utils/constants';

export default function TaskerSidebar() {
  const [threads, setThreads] = useState([]);
  const accessToken = useSelector((state) => state.accessToken);
  const navigate = useNavigate();

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
    <aside className="tasker-sidebar" aria-label="Tasker workspace">
      <button className="tasker-brand" onClick={() => navigate('/')} aria-label="Open Tasker home">
        <span className="tasker-mark" aria-hidden="true">T</span>
        <span>
          <strong>Tasker</strong>
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
              <span>{thread.title}</span>
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
