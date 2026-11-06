import React, { useEffect, useState } from 'react';

// Small, unobtrusive updater pill. Only renders inside the packaged Electron app.
const Labels = {
  available: 'Update downloading',
  downloaded: 'Restart to update',
  checking: 'Checking for updates',
  offline: 'Update check unavailable',
  error: 'Update check failed',
};

function UpdateStatusPill() {
  const [state, setState] = useState(null);

  useEffect(() => {
    const api = window.electronAPI;
    if (!api || typeof api.onUpdateStatus !== 'function') return undefined;
    const off = api.onUpdateStatus((evt) => setState(evt));
    if (typeof api.getUpdateState === 'function') {
      api.getUpdateState().then((s) => s && setState(s)).catch(() => {});
    }
    return off;
  }, []);

  if (!state || !Labels[state.status]) return null;

  const ready = state.status === 'downloaded';
  const text =
    (ready ? state.version : Labels[state.status]) +
    (state.status === 'available' && state.error ? ` ${state.error}` : '');

  return (
    <div
      style={{
        position: 'fixed', left: 12, bottom: 12, zIndex: 1800,
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 10px', borderRadius: 999, fontSize: 12, lineHeight: 1,
        color: '#fff', background: ready ? '#16a34a' : 'rgba(30,41,59,.88)',
        boxShadow: '0 2px 10px rgba(0,0,0,.25)', maxWidth: 260,
      }}
      title={state.error || text}
    >
      <span>{text}</span>
      {ready && (
        <button
          onClick={() => window.electronAPI.quitAndInstallUpdate()}
          style={{
            border: '1px solid rgba(255,255,255,.7)', background: 'transparent',
            color: '#fff', borderRadius: 999, fontSize: 12, padding: '3px 8px', cursor: 'pointer',
          }}
        >
          Restart
        </button>
      )}
    </div>
  );
}

export default UpdateStatusPill;
