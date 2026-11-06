const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  setToken: (token) => ipcRenderer.send('set-token', token),
  getToken: () => ipcRenderer.invoke('get-token'),
  deleteToken: () => ipcRenderer.send('delete-token'),
  setRefreshToken: (refreshToken) => ipcRenderer.send('set-refresh-token', refreshToken),
  getRefreshToken: () => ipcRenderer.invoke('get-refresh-token'),
  deleteRefreshToken: () => ipcRenderer.send('delete-refresh-token'),
  launchAIAgent: (baseURL, threadId, backgroundMode) => ipcRenderer.send('launch-ai-agent', baseURL, threadId, backgroundMode),
  stopAIAgent: () => ipcRenderer.send('stop-ai-agent'),
  onLogout: (callback) => ipcRenderer.on('trigger-logout', callback),
  onAIAgentExit: (callback) => ipcRenderer.on('ai-agent-exit', callback),
  onAIAgentLaunch: (callback) => ipcRenderer.on('ai-agent-launch', (_, threadId) => callback(threadId)),
  onAIAgentStatus: (callback) => {
    const handler = (_, event) => callback(event);
    ipcRenderer.on('ai-agent-status', handler);
    return () => ipcRenderer.removeListener('ai-agent-status', handler);
  },
  loginWithGoogle: () => ipcRenderer.invoke('login-with-google'),
  expandOverlay: (hasSuggestions) => ipcRenderer.send('expand-overlay', hasSuggestions),
  minimizeOverlay: () => ipcRenderer.send('minimize-overlay'),
  onCancelAllTasksTrigger: (callback) => ipcRenderer.on('trigger-cancel-all-tasks', callback),
  cancelAllTasksDone: () => ipcRenderer.send('cancel-all-tasks-done'),
  getSuggestions: (baseURL) => ipcRenderer.invoke('get-suggestions', baseURL),
  getLastBackgroundModeValue: () => ipcRenderer.invoke('get-last-background-mode-value'),
  getLastThinkingModeValue: () => ipcRenderer.invoke('get-last-thinking-mode-value'),
  setLastThinkingModeValue: (lastThinkingModeValue) => ipcRenderer.send('set-last-thinking-mode-value', lastThinkingModeValue),
  getHandsFreeValue: () => ipcRenderer.invoke('get-hands-free-value'),
  setHandsFreeValue: (value) => ipcRenderer.send('set-hands-free-value', value),
  setOverlayMode: (mode) => ipcRenderer.send('set-overlay-mode', mode),
  startBackgroundSetup: () => ipcRenderer.invoke('start-background-setup'),
  isBackgroundModeReady: () => ipcRenderer.invoke('check-background-ready'),
  onSetupStatus: (cb) => ipcRenderer.on('setup-status', (_, msg) => cb(msg)),
  onSetupProgress: (cb) => ipcRenderer.on('setup-progress', (_, pct) => cb(pct)),
  onSetupComplete: (cb) => ipcRenderer.on('setup-complete', (_, result) => cb(result)),
  getUpdateState: () => ipcRenderer.invoke('update:get-state'),
  checkForUpdates: () => ipcRenderer.invoke('update:check'),
  quitAndInstallUpdate: () => ipcRenderer.invoke('update:quit-and-install'),
  onUpdateStatus: (cb) => {
    const handler = (_, event) => cb(event);
    ipcRenderer.on('update-status', handler);
    return () => ipcRenderer.removeListener('update-status', handler);
  },
});
