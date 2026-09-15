#!/bin/bash

export DISPLAY=:99
unset WAYLAND_DISPLAY
chmod 1777 /tmp/.X11-unix
mkdir -p /agent/profile

echo "[*] Starting Xvfb..."
Xvfb :99 -screen 0 1280x720x24 &
sleep 2

echo "[*] Clearing previous Chrome session files..."
rm -f /agent/profile/Default/Last* /agent/profile/Default/Sessions/*

echo "[*] Launching Chromium with persistent profile..."
google-chrome-stable \
  --no-sandbox \
  --test-type \
  --disable-gpu \
  --disable-accelerated-2d-canvas \
  --disable-software-rasterizer \
  --force-device-scale-factor=1 \
  --window-size=1280,720 \
  --no-first-run \
  --restore-last-session=false \
  --disable-session-crashed-bubble \
  --disable-default-apps \
  --disable-notifications \
  --disable-features=TranslateUI \
  --user-data-dir=/agent/profile \
  https://www.google.com &

sleep 2

echo "[*] Starting VNC server..."
x11vnc -display :99 -rfbport 31583 -xkb -noxrecord -noxdamage -noxfixes -repeat -forever -listen -modtweak -capslock localhost &
sleep 2

echo "[*] Starting noVNC..."
/agent/noVNC/utils/novnc_proxy --vnc localhost:31583 --listen 39742
