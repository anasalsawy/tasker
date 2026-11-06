// Hands auto-update via GitHub Releases (anasalsawy/tasker).
// Never touches Railway: the updater channel is GitHub Releases only.
import { app, ipcMain, BrowserWindow } from 'electron';
// electron-updater is CommonJS and lazy-defines `autoUpdater` via
// Object.defineProperty, which cjs-module-lexer cannot detect as a named
// export. The packaged app loads main-process code as ESM, so a named import
// here throws "Named export 'autoUpdater' not found" before the window opens.
// Default-import the module namespace and destructure instead.
import updaterPkg from 'electron-updater';
import isDev from 'electron-is-dev';

const { autoUpdater } = updaterPkg;

const state = {
  status: 'idle', // idle | checking | available | downloaded | error | unsupported | offline
  version: null,
  error: null,
};

const emit = () => {
  for (const win of BrowserWindow.getAllWindows()) {
    pushUpdateStatus(win);
  }
};

const setStatus = (status, extra = {}) => {
  state.status = status;
  state.version = extra.version ?? state.version;
  state.error = extra.error ?? null;
  console.log(`[updater] ${status}${extra.version ? ' -> ' + extra.version : ''}${extra.error ? ' : ' + extra.error : ''}`);
  emit();
};

const sendNow = () => ({ ...state });

export function pushUpdateStatus(win) {
  if (!win || win.isDestroyed()) return;
  try {
    win.webContents.send('update-status', { ...state, type: 'sync' });
  } catch (err) {
    console.warn('[updater] status push failed:', err?.message);
  }
}

export function initAutoUpdater() {
  autoUpdater.autoDownload = true; // silent download; install happens on restart
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.disableWebInstaller = true;
  autoUpdater.logger = {
    info: (m) => console.log('[updater] ' + m),
    warn: (m) => console.warn('[updater] ' + m),
    error: (m) => console.error('[updater] ' + m),
    debug: (m) => console.log('[updater] ' + m),
  };

  autoUpdater.on('checking-for-update', () => setStatus('checking'));
  autoUpdater.on('update-available', (info) => {
    setStatus('available', { version: info.version });
  });
  autoUpdater.on('update-not-available', () => setStatus('idle'));
  autoUpdater.on('download-progress', (p) =>
    setStatus('available', { version: state.version, error: `${Math.round(p.percent)}%` })
  );
  autoUpdater.on('update-downloaded', (info) => {
    setStatus('downloaded', { version: info.version });
  });
  autoUpdater.on('error', (err) => {
    const msg = String((err && err.message) || err || 'unknown error');
    // Offline / DNS / 404 on releases are expected on a machine with no internet.
    if (/net::|ENOTFOUND|ECONNRESET|timeout|getaddrinfo|404|Not Found/i.test(msg)) {
      setStatus('offline', { error: msg });
    } else {
      setStatus('error', { error: msg });
    }
  });

  ipcMain.handle('update:get-state', () => sendNow());
  ipcMain.handle('update:check', async () => {
    if (!app.isPackaged) {
      setStatus('unsupported', { error: 'not packaged' });
      return sendNow();
    }
    try {
      const r = await autoUpdater.checkForUpdates();
      return r ? sendNow() : sendNow();
    } catch (e) {
      setStatus('error', { error: String(e && e.message ? e.message : e) });
      return sendNow();
    }
  });
  ipcMain.handle('update:quit-and-install', () => {
    if (state.status !== 'downloaded') return false;
    setImmediate(() => autoUpdater.quitAndInstall(false, true));
    return true;
  });

  // Startup check + silent poll. Skipped in dev; GitHub provider needs a real install.
  if (app.isPackaged) {
    setTimeout(() => {
      autoUpdater.checkForUpdates().catch(() => setStatus('offline', { error: 'startup check failed' }));
    }, 5000);
    setInterval(() => {
      if (state.status !== 'downloaded') {
        autoUpdater.checkForUpdates().catch(() => {});
      }
    }, 1000 * 60 * 60 * 6);
  } else {
    setStatus('unsupported', { error: 'dev build' });
  }
}
