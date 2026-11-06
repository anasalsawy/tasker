import { app, BrowserWindow, Menu, ipcMain, dialog, screen } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';
import isDev from 'electron-is-dev';
import Store from 'electron-store';
import constants from './electron/utils/constants.js';
import { spawn, exec, execSync } from 'child_process';
import { generatePKCE } from './electron/utils/oauth.js';
import express from 'express';
import kill from 'tree-kill';
import url from 'url';
import http from 'http';
import { v4 as uuidv4 } from 'uuid';
import { setupBackgroundMode, isBackgroundModeReady } from './electron/utils/wslSetup.js';
import { initAutoUpdater, pushUpdateStatus } from './electron/utils/autoUpdate.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const store = new Store();

let mainWindow;
let overlayWindow;
let aiagentProcess;
let aiagentIsBackground = false;
let backgroundAuthWindow;
let bgAuthProcess;
let bgAgentWindow;
let bgSetupWindow;
let readyToClose = false;
// Hands overlay state (see OVERLAY geometry + applyOverlayBounds below)
let overlayExpanded = false;
let overlayHasSuggestions = false;
let overlayPreferredMode = 'bar'; // 'bar' | 'chat' | 'pet' — reported by the renderer

function ensureDeviceId() {
  let deviceId = store.get(constants.DEVICE_ID_STORE_KEY);
  if (!deviceId) {
    deviceId = uuidv4();
    store.set(constants.DEVICE_ID_STORE_KEY, deviceId);
    console.log(`[Device ID created]: ${deviceId}`);
  } else {
    console.log(`[Device ID exists]: ${deviceId}`);
  }
}


ipcMain.on('set-token', (_, token) => {
  store.set(constants.ACCESS_TOKEN_STORE_KEY, token);
  if (!overlayWindow) {
    createOverlayWindow();
  }
});

ipcMain.handle('get-token', () => store.get(constants.ACCESS_TOKEN_STORE_KEY));
ipcMain.on('delete-token', () => {
  store.delete(constants.ACCESS_TOKEN_STORE_KEY);
  if (overlayWindow) {
    overlayWindow.close();
  }
});
ipcMain.on('set-refresh-token', (_, token) => store.set(constants.REFRESH_TOKEN_STORE_KEY, token));
ipcMain.handle('get-refresh-token', () => store.get(constants.REFRESH_TOKEN_STORE_KEY));
ipcMain.on('delete-refresh-token', () => store.delete(constants.REFRESH_TOKEN_STORE_KEY));

ipcMain.on('expand-overlay', (_, hasSuggestions) => {
  console.log("[Main Process] Received 'expand-overlay' IPC message.");
  expandMinimizeOverlay(true, hasSuggestions);
});

// Hands — task-gated collapse of the overlay window itself.
// renderer reports 'bar' | 'chat' | 'pet'; we resize the always-on-top window
// so execution shows as a compact strip and plain chat/conversation never
// grows into an execution surface.
ipcMain.on('set-overlay-mode', (_, mode) => {
  overlayPreferredMode = mode === 'pet' ? 'pet' : (mode === 'chat' ? 'chat' : 'bar');
  applyOverlayBounds();
});

ipcMain.handle('get-last-background-mode-value', () => store.get(constants.LAST_BACKGROUND_MODE_VALUE));
ipcMain.handle('get-last-thinking-mode-value', () => store.get(constants.LAST_THINKING_MODE_VALUE));
ipcMain.on('set-last-thinking-mode-value', (_, lastThinkingModeValue) => store.set(constants.LAST_THINKING_MODE_VALUE, lastThinkingModeValue));

// Hands-free (always-open voice channel) — operator toggle, default on.
ipcMain.handle('get-hands-free-value', () => {
  const v = store.get(constants.HANDS_FREE_STORE_KEY);
  return v === undefined ? 'true' : String(v);
});
ipcMain.on('set-hands-free-value', (_, value) => store.set(constants.HANDS_FREE_STORE_KEY, String(value)));

// Handle MINIMIZE request
ipcMain.on('minimize-overlay', () => {
  console.log("[Main Process] Received 'minimize-overlay' IPC message.");
  expandMinimizeOverlay(false);
});

ipcMain.handle('check-background-ready', () => {
  return isBackgroundModeReady();
});

ipcMain.handle('start-background-setup', async () => {
  // Prevent duplicate windows
  if (bgSetupWindow && !bgSetupWindow.isDestroyed()) {
    bgSetupWindow.focus();
    return;
  }

  bgSetupWindow = new BrowserWindow({
    width: 600,
    height: 300,
    title: 'Setting up Background Mode',
    resizable: false,
    modal: true,
    icon: path.join(__dirname, 'assets', process.platform === 'win32' ? 'icon.ico' : 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'electron', 'preload.js'),
      contextIsolation: true,
    },
  });

  const bgSetupUrl = isDev
    ? 'http://localhost:6763/#/background-setup'
    : `file://${path.join(__dirname, 'neuralagent-app', 'build', 'index.html')}#/background-setup`;

  bgSetupWindow.loadURL(bgSetupUrl);

  bgSetupWindow.on('closed', () => {
    bgSetupWindow = null;
  });

  const defaultErr = 'Setup Failed: Please ensure you have Windows 10 or higher and that virtualization is enabled in BIOS.';

  let result = { success: false, error: defaultErr };

  try {
    result = await setupBackgroundMode({
      onStatus: (msg) => {
        if (!bgSetupWindow?.isDestroyed()) {
          bgSetupWindow.webContents.send('setup-status', msg);
        }
      },
      onProgress: (pct) => {
        if (!bgSetupWindow?.isDestroyed()) {
          bgSetupWindow.webContents.send('setup-progress', pct);
        }
      },
    });
  } catch (err) {
    console.error('❌ Setup failed:', err);
    result = {
      success: false,
      error: err?.message || defaultErr,
    };
  }

  if (bgSetupWindow && !bgSetupWindow.isDestroyed()) {
    bgSetupWindow.webContents.send('setup-complete', result);
  }

  if (result.success) {
    launchBackgroundAuthWindow();
  }

  return result;
});


ipcMain.handle('get-suggestions', async (_, baseURL) => {
  return new Promise((resolve, reject) => {

    // const suggestor = spawn('./aiagent/venv/Scripts/python', ['./aiagent/suggestor.py'], {
    //   env: {
    //     NEURALAGENT_API_URL: baseURL,
    //     NEURALAGENT_USER_ACCESS_TOKEN: store.get(constants.ACCESS_TOKEN_STORE_KEY),
    //   },
    // });

    const isWindows = process.platform === 'win32';
    const isMac = process.platform === 'darwin';

    const suggestorPath = isDev
    ? path.join(__dirname, 'agent_build', isWindows ? 'suggestor.exe' : 'suggestor')
    : path.join(process.resourcesPath, isWindows ? 'suggestor.exe' : 'suggestor');

    const suggestor = spawn(suggestorPath, [], {
      env: {
        NEURALAGENT_API_URL: baseURL,
        NEURALAGENT_USER_ACCESS_TOKEN: store.get(constants.ACCESS_TOKEN_STORE_KEY),
      },
    });

    let output = '';
    let errorOutput = '';

    suggestor.stdout.on('data', (data) => {
      output += data.toString();
    });

    suggestor.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });

    suggestor.on('close', (code) => {
      if (code === 0) {
        try {
          const result = JSON.parse(output);
          resolve(result);
        } catch (err) {
          console.error('❌ Failed to parse suggestor output:', output);
          reject(err);
        }
      } else {
        console.error('❌ Suggestor exited with error:', errorOutput);
        reject(new Error('Suggestor failed'));
      }
    });
  });
});

ipcMain.on('launch-ai-agent', async (_, baseURL, threadId, backgroundMode) => {
  const isWindows = process.platform === 'win32';
  const isMac = process.platform === 'darwin';

  store.set(constants.LAST_BACKGROUND_MODE_VALUE, backgroundMode.toString());
  aiagentIsBackground = Boolean(backgroundMode);

  if (!backgroundMode) {
    if (aiagentProcess && !aiagentProcess.killed) {
      kill(aiagentProcess.pid, 'SIGKILL', () => {});
      aiagentProcess = null;
    }
    // Tasker uses the user's persistent Python installation in development.
    // Set TASKER_PYTHON to an explicit interpreter when several are installed.
    let pythonCommand = process.env.TASKER_PYTHON || (isWindows ? 'py' : 'python3');
    if (isWindows && !process.env.TASKER_PYTHON) {
      try {
        pythonCommand = execSync('py -c "import sys; print(sys.executable)"', {
          encoding: 'utf8', windowsHide: true,
        }).trim();
      } catch (error) {
        console.error('Could not resolve Tasker Python interpreter:', error);
      }
    }
    const agentScript = path.join(__dirname, 'aiagent', 'main.py');
    aiagentProcess = spawn(pythonCommand, [agentScript], {
      cwd: __dirname,
      env: {
        ...process.env,
        NEURALAGENT_API_URL: baseURL,
        NEURALAGENT_THREAD_ID: threadId,
        NEURALAGENT_USER_ACCESS_TOKEN: store.get(constants.ACCESS_TOKEN_STORE_KEY),
        TASKER_DUAL_LOBE_PROFILE: 'off',
        PYTHONUTF8: '1',
      },
    });

    // const agentPath = isDev
    // ? path.join(__dirname, 'agent_build', isWindows ? 'agent.exe' : 'agent')
    // : path.join(process.resourcesPath, isWindows ? 'agent.exe' : 'agent');

    // aiagentProcess = spawn(agentPath, [], {
    //   env: {
    //     NEURALAGENT_API_URL: baseURL,
    //     NEURALAGENT_THREAD_ID: threadId,
    //     NEURALAGENT_USER_ACCESS_TOKEN: store.get(constants.ACCESS_TOKEN_STORE_KEY),
    //   },
    // });
    mainWindow?.minimize();
  } else {
    // VERY IMPORTANT
    const envVars = {
      NEURALAGENT_API_URL: baseURL, // 'http://192.168.8.101:8000',
      NEURALAGENT_THREAD_ID: threadId,
      NEURALAGENT_USER_ACCESS_TOKEN: store.get(constants.ACCESS_TOKEN_STORE_KEY),
      SKIP_LLM_API_KEY_VERIFICATION: 'true',
      PYTHONUTF8: '1',
    };

    const shellCommand = Object.entries(envVars)
      .map(([k, v]) => `${k}="${v}"`).join(' ') + ' bash /agent/launch_bg_agent.sh';

    aiagentProcess = spawn('wsl', ['-d', 'NeuralOS', '--', 'bash', '-c', shellCommand]);

    launchBackgroundAgentWindow();
  }

  mainWindow?.webContents.send('ai-agent-launch', threadId);
  overlayWindow?.webContents.send('ai-agent-launch', threadId);
  expandMinimizeOverlay(true, false);

  let agentStdoutBuffer = '';
  aiagentProcess.stdout.on('data', (data) => {
    const text = data.toString();
    console.log(`[Agent stdout]: ${text}`);
    agentStdoutBuffer += text;
    const lines = agentStdoutBuffer.split(/\r?\n/);
    agentStdoutBuffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.startsWith('TASKER_EVENT:')) continue;
      try {
        const event = JSON.parse(line.slice('TASKER_EVENT:'.length));
        mainWindow?.webContents.send('ai-agent-status', event);
        overlayWindow?.webContents.send('ai-agent-status', event);
      } catch (error) {
        console.error('Could not parse Tasker progress event:', error);
      }
    }
  });
  aiagentProcess.stderr.on('data', (data) => {
    const message = data.toString();
    console.error(`[Agent stderr]: ${message}`);
    mainWindow?.webContents.send('ai-agent-status', {
      message: message.trim().split(/\r?\n/).slice(-1)[0] || 'Desktop agent error',
      level: 'error',
      timestamp: Date.now() / 1000,
    });
  });

  aiagentProcess.on('error', err => {
    console.error('❌  Agent process failed to start:', err);
    mainWindow?.webContents.send('trigger-cancel-all-tasks');
  });

  aiagentProcess.on('exit', (code, signal) => {
    console.log(`[Agent exited with code ${code}]`);
    if (bgAgentWindow) {
      bgAgentWindow.close();
    }
    if (aiagentIsBackground) {
      cleanupBGAgent();
    }
    if (mainWindow?.isMinimized()) {
      mainWindow.restore();
    }
    if (mainWindow) {
      mainWindow.focus();
    }
    mainWindow?.webContents.send('ai-agent-exit');
    overlayWindow?.webContents.send('ai-agent-exit');

    if (code !== 0 || signal) {
      mainWindow?.webContents.send('trigger-cancel-all-tasks');
    }
    aiagentProcess = null;
    aiagentIsBackground = false;
  });
});

ipcMain.on('stop-ai-agent', () => {
  if (aiagentProcess && !aiagentProcess.killed) {
    kill(aiagentProcess.pid, 'SIGKILL', (err) => {
      if (err) console.error('❌ Failed to kill agent:', err);
      else console.log('[✅ Agent forcibly stopped]');
    });
  }
  aiagentProcess = null;
  if (aiagentIsBackground) {
    cleanupBGAgent();
  }
  aiagentIsBackground = false;
});

const GOOGLE_CLIENT_ID = '296264060339-jamhdgfckblr0qgq360t5ok4e1kede35.apps.googleusercontent.com';
const REDIRECT_URI = 'http://127.0.0.1:36478';

function openUrlInBrowser(targetUrl) {
  const platform = process.platform;
  const command =
    platform === 'win32'
      ? `start "" "${targetUrl}"`
      : platform === 'darwin'
      ? `open "${targetUrl}"`
      : `xdg-open "${targetUrl}"`;
  exec(command);
}

ipcMain.handle('login-with-google', async () => {
  const { codeVerifier, codeChallenge } = generatePKCE();

  const authUrl = `https://accounts.google.com/o/oauth2/v2/auth` +
    `?client_id=${GOOGLE_CLIENT_ID}` +
    `&redirect_uri=${encodeURIComponent(REDIRECT_URI)}` +
    `&response_type=code` +
    `&scope=openid%20email%20profile` +
    `&code_challenge=${codeChallenge}` +
    `&code_challenge_method=S256` +
    `&access_type=offline`;

  openUrlInBrowser(authUrl);

  const appExpress = express();

  return new Promise((resolve, reject) => {
    const server = appExpress.listen(36478, () => {
      console.log('Listening for Google OAuth callback...');
    });

    appExpress.get('/', (req, res) => {
      const code = req.query.code;
      if (!code) {
        res.send('Login failed.');
        server.close();
        return reject('No code received');
      }

      res.send('Login successful! You can close this window.');
      server.close();
      resolve({ code, codeVerifier });
    });
  });
});

const createAppMenu = () => {
  const template = [
    {
      label: 'App',
      submenu: [
        {
          label: 'Background Mode Authentication',
          click: () => {
            if ((aiagentProcess && !aiagentProcess.killed) || (bgAuthProcess && !bgAuthProcess.killed)) {
              return;
            }
            launchBackgroundAuthWindow();
          },
        },
        {
          label: 'Logout',
          click: () => {
            if (overlayWindow) {
              overlayWindow.close();
            }
            mainWindow?.webContents.send('trigger-logout');
          },
        },
        { role: 'quit' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'togglefullscreen' },
        // { role: 'toggledevtools' },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
};

function startBackgroundAuthServices() {
  bgAuthProcess = spawn('wsl', ['-d', 'NeuralOS', '--', 'bash', '/agent/background_mode_authentication.sh']);

  bgAuthProcess.stdout.on('data', data => {
    console.log(`[BG Auth]: ${data.toString()}`);
  });

  bgAuthProcess.stderr.on('data', data => {
    console.error(`[BG Auth ERROR]: ${data.toString()}`);
  });
}

function cleanupBackgroundAuthServices() {
  try {
    execSync('wsl -d NeuralOS -- bash /agent/background_mode_authentication_cleanup.sh');
    console.log('[BG Auth]: Cleanup script executed.');
  } catch (err) {
    console.error('[BG Auth]: Cleanup failed:', err);
  }

  if (bgAuthProcess) {
    if (!bgAuthProcess.killed) {
      bgAuthProcess.kill('SIGKILL');
    }
  }
  bgAuthProcess = null;
}

function cleanupBGAgent() {
  try {
    execSync('wsl -d NeuralOS -- bash /agent/stop_bg_agent.sh');
    console.log('[BG Agent]: Cleanup script executed.');
  } catch (err) {
    console.error('[BG Agent]: Cleanup failed:', err);
  }

  if (aiagentProcess) {
    if (!aiagentProcess.killed) {
      aiagentProcess.kill('SIGKILL');
    }
  }
}

function waitForNoVNCPortReady(port, timeout = 10000, interval = 300) {
  const deadline = Date.now() + timeout;

  return new Promise((resolve, reject) => {
    const check = () => {
      const req = http.get({ hostname: '127.0.0.1', port, path: '/', timeout: 1000 }, (res) => {
        res.destroy();
        resolve(true); // Port is ready
      });

      req.on('error', (err) => {
        if (Date.now() > deadline) return reject(new Error('Timed out waiting for noVNC'));
        setTimeout(check, interval);
      });

      req.end();
    };

    check();
  });
}

function launchBackgroundAuthWindow() {
  if (backgroundAuthWindow) return;

  startBackgroundAuthServices();

  waitForNoVNCPortReady(39742, 20000)
    .then(() => {
      backgroundAuthWindow = new BrowserWindow({
        width: 1350,
        height: 780,
        title: 'Hands Background Auth',
        icon: path.join(__dirname, 'assets', process.platform === 'win32' ? 'icon.ico' : 'icon.png'),
        webPreferences: {
          contextIsolation: true,
          nodeIntegration: false,
          preload: path.join(__dirname, 'electron', 'preload.js'),
        },
      });

      const reactURL = isDev
        ? 'http://localhost:6763/#/background-auth'
        : `file://${path.join(__dirname, 'neuralagent-app', 'build', 'index.html')}#/background-auth`;

      backgroundAuthWindow.loadURL(reactURL);

      backgroundAuthWindow.on('closed', () => {
        cleanupBackgroundAuthServices();
        backgroundAuthWindow = null;
      });
    })
    .catch((err) => {
      console.error('❌ noVNC failed to start:', err);
      cleanupBackgroundAuthServices();
    });
}

function launchBackgroundAgentWindow() {
  if (bgAgentWindow) return;

  waitForNoVNCPortReady(39742, 20000)
    .then(() => {
      bgAgentWindow = new BrowserWindow({
        width: 1350,
        height: 780,
        title: 'Hands Background Task',
        icon: path.join(__dirname, 'assets', process.platform === 'win32' ? 'icon.ico' : 'icon.png'),
        webPreferences: {
          contextIsolation: true,
          nodeIntegration: false,
          preload: path.join(__dirname, 'electron', 'preload.js'),
        },
      });

      const reactURL = isDev
        ? 'http://localhost:6763/#/background-task'
        : `file://${path.join(__dirname, 'neuralagent-app', 'build', 'index.html')}#/background-task`;

      bgAgentWindow.loadURL(reactURL);

      bgAgentWindow.on('closed', () => {
        bgAgentWindow = null;
      });
    })
    .catch((err) => {
      console.error('noVNC failed to start:', err);
    });
}

function createWindow() {
  if (mainWindow) return;
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 700,
    icon: path.join(__dirname, 'assets', process.platform === 'win32' ? 'icon.ico' : 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'electron', 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const startURL = isDev
    ? 'http://localhost:6763'
    : url.format({
        pathname: path.join(__dirname, 'neuralagent-app', 'build', 'index.html'),
        protocol: 'file:',
        slashes: true,
      });

  mainWindow.loadURL(startURL);

  mainWindow.webContents.on('did-finish-load', () => {
    pushUpdateStatus(mainWindow);
  });

  mainWindow.on('close', async (e) => {
    if (readyToClose) return;

    e.preventDefault();
    if (mainWindow?.webContents) {
      mainWindow?.webContents.send('trigger-cancel-all-tasks');
    }

    ipcMain.once('cancel-all-tasks-done', () => {
      readyToClose = true;
      mainWindow.close();
    });
  });

  mainWindow.on('closed', () => {
    mainWindow = null;

    if (overlayWindow && !overlayWindow.isDestroyed()) {
      overlayWindow.close();
    }
    if (bgAgentWindow && !bgAgentWindow.isDestroyed()) {
      bgAgentWindow.close();
    }
    if (bgSetupWindow && !bgSetupWindow.isDestroyed()) {
      bgSetupWindow.close();
    }
    if (backgroundAuthWindow && !backgroundAuthWindow.isDestroyed()) {
      backgroundAuthWindow.close();
    }
  });
}

function createOverlayWindow() {
  if (overlayWindow) return;

  const windowWidth = 60;
  const windowHeight = 60;
  const margin = 25;

  const primaryDisplay = screen.getPrimaryDisplay();
  const { width: screenWidth, height: screenHeight } = primaryDisplay.workArea;

  const xPos = screenWidth - windowWidth - margin;
  const yPos = screenHeight - windowHeight - margin;

  overlayWindow = new BrowserWindow({
    width: 60,
    height: 60,
    x: xPos,
    y: yPos,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    webPreferences: {
      preload: path.join(__dirname, 'electron', 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const overlayURL = isDev
    ? 'http://localhost:6763/#/overlay'
    : `file://${path.join(__dirname, 'neuralagent-app', 'build', 'index.html')}#/overlay`;

  overlayWindow.loadURL(overlayURL);

  overlayWindow.on('closed', () => {
    overlayWindow = null;
  });
}

// Overlay geometry. Hands rule: the window only grows into an execution strip
// when the RENDERER declares mode==='pet' (task recognized post-hoc); plain
// chat/conversation keeps the compact footprint. Sizes:
//   idle chip       60x60    (default 'bar' face)
//   execution pet  320x64    (compact strip, corner-pinned, never obscures)
//   chat-expanded  376xH     (H grows with suggestions only, not with tasks)
const OVERLAY = {
  idle: { w: 60, h: 60 },
  pet: { w: 320, h: 64 },
  chat: { w: 376, h: 64 },
  chatSuggestions: { w: 376, h: 392 },
  margin: 25,
};

function expandMinimizeOverlay(expanded, hasSuggestions = false) {
  overlayExpanded = Boolean(expanded);
  overlayHasSuggestions = Boolean(hasSuggestions);
  applyOverlayBounds();
}

function applyOverlayBounds() {
  if (!overlayWindow || overlayWindow.isDestroyed()) return;

  let size;
  if (overlayExpanded && overlayHasSuggestions) size = OVERLAY.chatSuggestions;
  else if (overlayExpanded && overlayPreferredMode !== 'bar') size = OVERLAY.chat;
  else if (!overlayExpanded && overlayPreferredMode === 'pet') size = OVERLAY.pet;
  else size = OVERLAY.idle;

  const { width: SW, height: SH } = screen.getPrimaryDisplay().workArea;
  const X = SW - size.w - OVERLAY.margin;
  const Y = SH - size.h - OVERLAY.margin;

  overlayWindow.setBounds({ x: X, y: Y, width: size.w, height: size.h }, true);
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

app.whenReady().then(() => {
  ensureDeviceId();
  initAutoUpdater();
  createWindow();
  if (store.get(constants.ACCESS_TOKEN_STORE_KEY)) {
    createOverlayWindow();
  }
  createAppMenu();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
      createOverlayWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (aiagentProcess && !aiagentProcess.killed) {
    kill(aiagentProcess.pid, 'SIGKILL', (err) => {
      if (err) console.error('❌ Failed to kill agent:', err);
      else console.log('[Agent stopped on app exit]');
    });
  }
  if (process.platform !== 'darwin') app.quit();
});
