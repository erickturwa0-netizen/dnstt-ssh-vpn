#!/usr/bin/env bash
# DNSTT + SSH VPN - one-shot installer for Linux (Mint/Ubuntu/Debian)
# Installs: system deps, dnstt-client, tun2socks, desktop launcher
set -euo pipefail

APP_DIR="${HOME}/Apps/dnstt-ssh-vpn"
BIN_DIR="/usr/local/bin"
DESKTOP="${HOME}/.local/share/applications/dnstt-ssh-vpn.desktop"
ARCH="$(uname -m)"

case "$ARCH" in
  x86_64|amd64)  GOARCH=amd64 ;;
  aarch64|arm64) GOARCH=arm64 ;;
  *)
    echo "Architecture isiyoungwa: $ARCH (inahitaji amd64 au arm64)"
    exit 1
    ;;
esac

echo "==> Architecture: $ARCH ($GOARCH)"
echo "==> Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y python3-tk openssh-client sshpass iproute2 policykit-1 systemd-resolved curl unzip wget

# ---- App source ----
if [[ ! -d "$APP_DIR" ]]; then
  echo "==> Cloning app..."
  mkdir -p "$(dirname "$APP_DIR")"
  git clone https://github.com/erickturwa0-netizen/dnstt-ssh-vpn.git "$APP_DIR"
else
  echo "==> Updating app..."
  git -C "$APP_DIR" pull --ff-only || true
fi
chmod +x "$APP_DIR/dnstt_ssh_vpn.py"

# ---- dnstt-client ----
echo "==> Downloading dnstt-client ($GOARCH)..."
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

DNSTT_URL="https://github.com/net2share/dnstt/releases/latest/download/dnstt-client-linux-${GOARCH}"
if curl -fsSL -o "$TMP/dnstt-client" "$DNSTT_URL"; then
  sudo install -m 755 "$TMP/dnstt-client" "$BIN_DIR/dnstt-client"
  echo "    dnstt-client -> $BIN_DIR/dnstt-client"
else
  echo "WARNING: dnstt-client download failed from net2share."
  echo "         Unaweza kujenga mwenyewe: https://www.bamsoftware.com/software/dnstt/"
fi

# ---- tun2socks ----
echo "==> Downloading tun2socks ($GOARCH)..."
T2S_ZIP="tun2socks-linux-${GOARCH}.zip"
T2S_URL="https://github.com/xjasonlyu/tun2socks/releases/latest/download/${T2S_ZIP}"
if curl -fsSL -o "$TMP/$T2S_ZIP" "$T2S_URL"; then
  unzip -qo "$TMP/$T2S_ZIP" -d "$TMP"
  # zip inaweza kuwa na jina la binary tofauti kidogo
  BIN=$(find "$TMP" -maxdepth 1 -type f -name 'tun2socks*' ! -name '*.zip' | head -1)
  if [[ -n "$BIN" ]]; then
    sudo install -m 755 "$BIN" "$BIN_DIR/tun2socks"
    echo "    tun2socks -> $BIN_DIR/tun2socks"
  else
    echo "WARNING: tun2socks binary haikupatikana ndani ya zip"
  fi
else
  echo "WARNING: tun2socks download failed"
fi

# ---- Desktop launcher ----
echo "==> Creating desktop launcher..."
mkdir -p "$(dirname "$DESKTOP")"
cat > "$DESKTOP" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=DNSTT + SSH VPN
Comment=Full-system DNSTT + SSH VPN for Linux
Exec=python3 ${APP_DIR}/dnstt_ssh_vpn.py
Icon=network-vpn
Terminal=false
Categories=Network;Security;
StartupNotify=true
EOF
update-desktop-database "$(dirname "$DESKTOP")" 2>/dev/null || true

echo ""
echo "========================================"
echo "  Installation complete!"
echo "========================================"
echo "  App:      $APP_DIR"
echo "  dnstt:    $(command -v dnstt-client 2>/dev/null || echo 'NOT FOUND')"
echo "  tun2socks:$(command -v tun2socks 2>/dev/null || echo 'NOT FOUND')"
echo "  Menu:     DNSTT + SSH VPN"
echo ""
echo "  Anzisha:  python3 $APP_DIR/dnstt_ssh_vpn.py"
echo "  au tafuta 'DNSTT' kwenye menu."
echo "========================================"
