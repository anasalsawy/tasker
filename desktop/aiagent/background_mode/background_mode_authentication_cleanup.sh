#!/bin/bash

echo "[*] Cleaning up background auth session..."

# Ensure temp path exists
SESSION_TMP_DIR="/tmp/remote-session"
mkdir -p "$SESSION_TMP_DIR"

# Kill by PID file
for name in xvfb chrome x11vnc novnc; do
  PIDFILE="$SESSION_TMP_DIR/$name.pid"
  if [[ -f "$PIDFILE" ]]; then
    PID=$(cat "$PIDFILE")
    if ps -p "$PID" > /dev/null 2>&1; then
      echo " - Killing $name (PID $PID)"
      sudo kill "$PID"
      sleep 1
      sudo pkill -P "$PID"
    else
      echo " - PID $PID for $name is not active"
    fi
    rm -f "$PIDFILE"
  else
    echo " - No PID file found for $name"
  fi
done

echo "[*] Killing any remaining background auth processes..."

# Use sudo to ensure permission even if chrome runs as root
sudo pkill -f "Xvfb.*:99" 2>/dev/null
sudo pkill -f "google-chrome-stable.*--user-data-dir=/agent/profile" 2>/dev/null
sudo pkill -f "x11vnc.*-display :99" 2>/dev/null
sudo pkill -f "novnc_proxy" 2>/dev/null

# Force kill if Chrome still running
sleep 1
if pgrep -f "google-chrome" > /dev/null; then
  echo "⚠️ Chrome still running — forcing kill"
  sudo pkill -9 -f "google-chrome"
fi

echo "[*] Cleaning up temporary session files..."
sudo rm -rf "$SESSION_TMP_DIR"

echo "[✓] Background auth session cleaned."
