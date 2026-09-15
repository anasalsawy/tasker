#!/bin/bash
set -e

echo "[*] Updating package index..."
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y universe
sudo add-apt-repository -y multiverse
sudo apt update

echo "[*] Installing runtime packages..."
sudo apt install -y \
  ca-certificates \
  nano \
  curl \
  gnupg \
  software-properties-common \
  x11vnc \
  xvfb \
  xfonts-base \
  x11-utils \
  xdotool \
  scrot \
  fonts-liberation \
  fonts-dejavu-core \
  fonts-dejavu-extra \
  fonts-noto-core \
  fonts-noto-cjk \
  fonts-noto-color-emoji \
  unzip \
  wget \
  locales \
  python3-minimal  # needed for noVNC's bundled websockify

echo "[*] Setting up UTF-8 locale..."
sudo locale-gen en_US.UTF-8
sudo update-locale LANG=en_US.UTF-8

echo "[*] Installing Google Chrome..."
if ! command -v google-chrome-stable &> /dev/null; then
  wget -q -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  sudo dpkg -i /tmp/google-chrome.deb || sudo apt --fix-broken install -y
  rm /tmp/google-chrome.deb
fi

mkdir -p /agent/profile

echo "[*] Installing noVNC and websockify..."

# Download noVNC
cd /agent
wget https://github.com/novnc/noVNC/archive/refs/heads/master.zip -O noVNC.zip
unzip noVNC.zip
mv noVNC-* noVNC
rm noVNC.zip

# Download websockify into noVNC/utils/
mkdir -p /agent/noVNC/utils
cd /agent/noVNC/utils
wget https://github.com/novnc/websockify/archive/refs/heads/master.zip -O websockify.zip
unzip websockify.zip
mv websockify-* websockify
rm websockify.zip

# Make scripts executable
chmod +x /agent/noVNC/utils/novnc_proxy
chmod +x /agent/noVNC/utils/websockify/run

echo "[*] Cleaning up..."
sudo apt clean
sudo rm -rf /var/lib/apt/lists/*

echo "[✅] Setup complete: Chrome, Xvfb, VNC, noVNC, xdotool, scrot, fonts"
