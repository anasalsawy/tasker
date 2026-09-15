#!/bin/bash

echo "[*] Stopping NeuralAgent background session..."

# Kill processes using PID files
for name in xvfb chrome vnc novnc aiagent; do
  PIDFILE="/tmp/bg_${name}.pid"
  if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if ps -p "$PID" > /dev/null 2>&1; then
      echo " - Killing $name (PID $PID)"
      sudo kill "$PID"
      sleep 1
      sudo pkill -P "$PID"
    else
      echo " - PID $PID for $name is not running"
    fi
    rm -f "$PIDFILE"
  else
    echo " - No PID file found for $name"
  fi
done

echo "[*] Killing any remaining known background processes..."
sudo pkill -f "Xvfb.*:99" 2>/dev/null
sudo pkill -f "google-chrome-stable" 2>/dev/null
sudo pkill -f "x11vnc.*-display :99" 2>/dev/null
sudo pkill -f "novnc_proxy" 2>/dev/null
sudo pkill -f "/agent/aiagent/main.py" 2>/dev/null

# 🔒 Force kill all chrome if anything still running
sleep 1
if pgrep -f "google-chrome" > /dev/null; then
  echo "⚠️ Chrome still running — forcing shutdown..."
  sudo pkill -9 -f "google-chrome"
fi

echo "[✓] Background cleanup complete."
