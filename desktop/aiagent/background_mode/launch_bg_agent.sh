#!/bin/bash

export DISPLAY=:99
unset WAYLAND_DISPLAY
mkdir -p /agent/profile

echo "[*] Starting Xvfb..."
Xvfb :99 -screen 0 1280x720x24 -nolisten tcp &
echo $! > /tmp/bg_xvfb.pid

# Wait until Xvfb is ready
tries=0
while ! xdpyinfo -display :99 >/dev/null 2>&1; do
  sleep 0.5
  tries=$((tries + 1))
  if [ "$tries" -gt 20 ]; then
    echo "❌ Xvfb failed to start."
    exit 1
  fi
done

echo "[*] Clearing previous Chrome session files..."
rm -f /agent/profile/Default/Last* /agent/profile/Default/Sessions/*

echo "[*] Launching Chromium with persistent profile and remote debugging..."
google-chrome-stable \
  --no-sandbox \
  --test-type \
  --disable-gpu \
  --disable-accelerated-2d-canvas \
  --force-device-scale-factor=1 \
  --remote-debugging-port=13783 \
  --user-data-dir=/agent/profile \
  --no-first-run \
  --restore-last-session=false \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --disable-default-apps \
  --disable-notifications \
  --window-size=1280,720 \
  https://www.google.com &

echo $! > /tmp/bg_chrome.pid
export BROWSER_CDP_URL=http://127.0.0.1:13783
sleep 2

echo "[*] Starting VNC server..."
x11vnc -display :99 -rfbport 31583 -xkb -noxrecord -noxdamage -noxfixes -repeat -modtweak -capslock -forever -listen localhost &
echo $! > /tmp/bg_vnc.pid
sleep 2

echo "[*] Starting noVNC..."
/agent/noVNC/utils/novnc_proxy --vnc localhost:31583 --listen 39742 &
echo $! > /tmp/bg_novnc.pid
sleep 2

echo "[*] Launching NeuralAgent AI agent..."
#/agent/aiagent/venv/bin/python /agent/aiagent/main.py
/agent/agent