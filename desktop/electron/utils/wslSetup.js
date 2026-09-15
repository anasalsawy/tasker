import fs from 'fs';
import path from 'path';
import https from 'https';
import { execSync } from 'child_process';
import sudo from 'sudo-prompt';

const distroName = 'NeuralOS';
const baseDir = 'C:\\ProgramData\\NeuralAgent\\wsl';
const imagePath = path.join(baseDir, 'neuralos.tar.gz');
const imageUrl = 'https://neuralagent-website-s3.s3.us-east-1.amazonaws.com/uploads/neuralos.tar.gz';

function tryExec(cmd, encoding = 'utf8') {
  try {
    const result = execSync(cmd, { encoding });
    console.log(`✔ ${cmd}\n${result}`);
    return result;
  } catch (err) {
    console.log(`❌ ${cmd}\n${err.message}`);
    return null;
  }
}

function isAdmin() {
  try {
    execSync('fsutil dirty query %systemdrive%', { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function checkWindowsVersion() {
  const version = tryExec('ver');
  return version && (version.includes('10.') || version.includes('11.'));
}

function isWSLInstalled() {
  return tryExec('wsl.exe --status', 'utf16le') !== null;
}

function installWSLWithElevation() {
  return new Promise((resolve) => {
    const options = { name: 'NeuralAgent Setup' };

    sudo.exec('wsl.exe --install --no-distribution --no-launch', options,
      (err, stdout, stderr) => {
        console.log(stdout || stderr || '');

        // Wait a bit then check if WSL is really installed
        setTimeout(() => {
          resolve(isWSLInstalled());
        }, 2000);
      }
    );
  });
}

function checkAndEnableFeatures() {
  return new Promise((resolve) => {
    const options = { name: 'NeuralAgent Setup' };

    const script = `
@echo off
setlocal enabledelayedexpansion

REM ---------- helper : test feature, language-independent ----------------
call :IsEnabled Microsoft-Windows-Subsystem-Linux
set WSL_OK=!ERRORLEVEL!
call :IsEnabled VirtualMachinePlatform
set VM_OK=!ERRORLEVEL!
set NEED_REBOOT=0

REM ---------- enable if missing -----------------------------------------
if "!WSL_OK!"=="0" (
  dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart >nul
  if %ERRORLEVEL% EQU 0 (
    set WSL_OK=1
    set NEED_REBOOT=1
  )
)
if "!VM_OK!"=="0" (
  dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart >nul
  if %ERRORLEVEL% EQU 0 (
    set VM_OK=1
    set NEED_REBOOT=1
  )
)

echo {"wsl": !WSL_OK!, "vm": !VM_OK!, "reboot": !NEED_REBOOT!}
exit /b 0

:IsEnabled
  powershell -NoLogo -NoProfile -Command ^
    "if((Get-WindowsOptionalFeature -Online -FeatureName '%~1').State -eq 'Enabled'){exit 0}else{exit 1}" >nul 2>&1
  if %ERRORLEVEL% EQU 0 (exit /b 1)

  REM ------- fallback: treat WSL runtime as proof -----------------------
  if /I "%~1"=="Microsoft-Windows-Subsystem-Linux" (
    wsl.exe --status >nul 2>&1
    if %ERRORLEVEL% EQU 0 exit /b 1
  )
  exit /b 0
`;
    sudo.exec(script, options, (err, stdout) => {
      if (err) {
        console.error('❌ Failed to check/enable features:', err);
        return resolve({ wsl: false, vm: false, reboot: false });
      }
      const json = (stdout.trim().match(/\{.*\}$/m) || ['{}'])[0];
      try { resolve(JSON.parse(json)); }
      catch { resolve({ wsl: false, vm: false, reboot: false }); }
    });
  });
}

function isDistroRegistered(distroName) {
  const result = tryExec('wsl.exe --list', 'utf16le');
  if (!result) return false;

  const lines = result.split('\n').slice(1); // skip header line
  const distros = lines.map(line => line.trim().split(' ')[0]); // normalize
  return distros.includes(distroName);
}

function downloadImage(progressCb) {
  return new Promise((resolve, reject) => {
    if (!fs.existsSync(baseDir)) fs.mkdirSync(baseDir, { recursive: true });
    const file = fs.createWriteStream(imagePath);

    https.get(imageUrl, (res) => {
      if (res.statusCode !== 200) {
        reject(new Error(`Download failed with status ${res.statusCode}`));
        return;
      }

      const total = parseInt(res.headers['content-length'], 10);
      let downloaded = 0;

      res.on('data', chunk => {
        downloaded += chunk.length;
        if (progressCb) progressCb(Math.round((downloaded / total) * 100));
      });

      res.pipe(file);

      file.on('finish', () => {
        file.close(() => {
          const stats = fs.statSync(imagePath);
          if (stats.size === 0) {
            reject(new Error('Downloaded file is empty!'));
          } else {
            resolve();
          }
        });
      });
    }).on('error', reject);
  });
}

function importDistro() {
  execSync(`wsl.exe --import ${distroName} "${baseDir}" "${imagePath}" --version 2`);
}

function verifyDistro() {
  execSync(`wsl.exe -d ${distroName} -- echo OK`);
}

export async function setupBackgroundMode({ onStatus, onProgress }) {
  try {
    if (!checkWindowsVersion()) {
      throw new Error('❌ NeuralAgent background mode requires Windows 10 or later.');
    }

    const log = (msg) => {
      console.log('[BG Setup]', msg);
      onStatus?.(msg);
    };

    const { wsl, vm, reboot } = await checkAndEnableFeatures();
    if (!wsl || !vm) {
      throw new Error(reboot
        ? '✅ Features enabled. Please reboot your PC and relaunch NeuralAgent.'
        : '❌ Failed to enable required features.');
    }

    if (!isWSLInstalled()) {
      log('Installing WSL…');
      const ok = await installWSLWithElevation();
      if (!ok) {
        throw new Error(
          '❌ Automatic WSL installation failed. ' +
          'Please install WSL from Microsoft Store or run “wsl --install” in an Administrator terminal.'
        );
      }
      log('✅ WSL runtime installed. Reboot might be required.');
      //throw new Error('✅ WSL installed. Please reboot your PC and relaunch NeuralAgent.');
    }

    // --- Import distro if needed ---
    if (!isDistroRegistered()) {
      log('Downloading NeuralAgent Runtime Environment...');
      await downloadImage(onProgress);
      log('Importing NeuralAgent Runtime Environment...');
      importDistro();
    }

    // --- Verify ---
    log('Verifying NeuralAgent Runtime Environment setup...');
    verifyDistro();
    log('✅ NeuralAgent Runtime Environment is ready.');

    return { success: true };

  } catch (err) {
    console.error('❌ Background mode setup failed:', err);
    return { success: false, error: err.message };
  }
}


export function isBackgroundModeReady() {
  return checkWindowsVersion() &&
    isWSLInstalled() &&
    isDistroRegistered('NeuralOS');
}
