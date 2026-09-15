#!/bin/bash

set -e

echo "[*] Updating package lists..."
sudo apt update

echo "[*] Installing base packages..."
sudo apt install -y \
  sudo wget curl gnupg lsb-release ca-certificates \
  software-properties-common apt-transport-https \
  fonts-noto fonts-noto-cjk fonts-noto-color-emoji \
  x11vnc xvfb x11-utils xdotool scrot \
  python3 python3-pip python3-venv \
  ffmpeg imagemagick

echo "[*] Installing language fonts (Arabic, Chinese, Emoji)..."
sudo apt install -y \
  fonts-noto \
  fonts-noto-cjk \
  fonts-noto-color-emoji \
  fonts-dejavu-core \
  fonts-dejavu-extra \
  fonts-kacst \
  fonts-sil-scheherazade \
  fonts-takao-gothic


echo "[*] Installing Google Chrome..."
if ! command -v google-chrome-stable &> /dev/null; then
  wget -q -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  sudo dpkg -i /tmp/google-chrome.deb || sudo apt --fix-broken install -y
  rm /tmp/google-chrome.deb
fi

mkdir -p /agent/profile

echo "[*] Setting up Python venv for NeuralAgent..."
cd /agent/aiagent
python3 -m venv venv
./venv/bin/pip install --upgrade pip setuptools wheel

if [ -f "requirements.txt" ]; then
  echo "[*] Installing Python dependencies..."
  ./venv/bin/pip install -r requirements.txt
fi

echo "[✓] Install completed successfully."
