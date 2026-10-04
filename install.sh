#!/usr/bin/env bash
# SlipNet Full-System VPN — installer for Linux Mint / Ubuntu / Debian
# Inaweka app kwenye MENU + Desktop (si terminal)
set -euo pipefail

APP_DIR="${HOME}/Apps/dnstt-ssh-vpn"
BIN_DIR="${HOME}/.local/bin"
SHARE_APP="${HOME}/.local/share/applications"
DESKTOP_FILE="${SHARE_APP}/slipnet-vpn.desktop"
DESKTOP_LINK="${HOME}/Desktop/slipnet-vpn.desktop"
WRAPPER="${BIN_DIR}/slipnet-vpn"
ARCH="$(uname -m)"

case "$ARCH" in
  x86_64|amd64)  GOARCH=amd64 ;;
  aarch64|arm64) GOARCH=arm64 ;;
  armv7*|armhf)  GOARCH=armv7 ;;
  *)
    echo "Architecture isiyoungwa: $ARCH"
    exit 1
    ;;
esac

echo "==> Architecture: $ARCH ($GOARCH)"
echo "==> System packages..."
sudo apt-get update -qq
sudo apt-get install -y python3-tk python3 openssh-client sshpass iproute2 policykit-1 \
  systemd-resolved curl unzip wget git desktop-file-utils 2>/dev/null \
  || sudo apt-get install -y python3-tk python3 openssh-client sshpass iproute2 policykit-1 curl unzip wget git

mkdir -p "$BIN_DIR" "$SHARE_APP" "${HOME}/.config/dnstt-ssh-vpn/bin"

# ---- App source ----
if [[ ! -d "$APP_DIR/.git" ]]; then
  echo "==> Cloning app..."
  mkdir -p "$(dirname "$APP_DIR")"
  rm -rf "$APP_DIR"
  git clone https://github.com/erickturwa0-netizen/dnstt-ssh-vpn.git "$APP_DIR"
else
  echo "==> Updating app..."
  git -C "$APP_DIR" pull --ff-only || true
fi
chmod +x "$APP_DIR/dnstt_ssh_vpn.py"

# ---- Wrapper (anza GUI bila terminal) ----
cat > "$WRAPPER" << EOF
#!/usr/bin/env bash
cd "$APP_DIR"
exec python3 "$APP_DIR/dnstt_ssh_vpn.py" "\$@"
EOF
chmod +x "$WRAPPER"

# Hakikisha ~/.local/bin iko PATH (session mpya)
if ! echo ":$PATH:" | grep -q ":$BIN_DIR:"; then
  if ! grep -q '.local/bin' "${HOME}/.profile" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.profile"
  fi
fi

# ---- Optional: slipnet CLI + tun2socks (app inaweza kupakua yenyewe pia) ----
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "==> tun2socks..."
T2S_ZIP="tun2socks-linux-${GOARCH}.zip"
if [[ "$GOARCH" == "armv7" ]]; then T2S_ZIP="tun2socks-linux-arm64.zip"; fi
if curl -fsSL -o "$TMP/$T2S_ZIP" \
  "https://github.com/xjasonlyu/tun2socks/releases/latest/download/${T2S_ZIP}"; then
  unzip -qo "$TMP/$T2S_ZIP" -d "$TMP"
  BIN=$(find "$TMP" -maxdepth 1 -type f -name 'tun2socks*' ! -name '*.zip' | head -1)
  if [[ -n "${BIN:-}" ]]; then
    install -m 755 "$BIN" "${HOME}/.config/dnstt-ssh-vpn/bin/tun2socks"
    echo "    tun2socks OK"
  fi
fi

echo "==> slipnet CLI..."
SN_NAME="slipnet-linux-${GOARCH}"
if curl -fsSL -o "$TMP/slipnet" \
  "https://github.com/anonvector/SlipNet/releases/download/v2.5.3/${SN_NAME}"; then
  install -m 755 "$TMP/slipnet" "${HOME}/.config/dnstt-ssh-vpn/bin/slipnet"
  echo "    slipnet OK"
else
  echo "    (slipnet itapakuliwa otomatiki unapoconnect)"
fi

# ---- .desktop (Menu + Desktop) ----
echo "==> Desktop application entry..."
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=SlipNet VPN
GenericName=VPN Client
Comment=SlipNet / DNSTT full-system VPN for Linux
Exec=${WRAPPER}
Icon=network-vpn
Terminal=false
Categories=Network;Security;Utility;
Keywords=vpn;slipnet;dnstt;proxy;tunnel;
StartupNotify=true
StartupWMClass=dnstt_ssh_vpn.py
EOF
chmod +x "$DESKTOP_FILE"

# Copy to Desktop (Linux Mint / Cinnamon)
mkdir -p "${HOME}/Desktop"
cp "$DESKTOP_FILE" "$DESKTOP_LINK"
chmod +x "$DESKTOP_LINK"

# Mark as trusted (Cinnamon / Nemo) — vinginevyo icon inaweza kuuliza "Trust"
if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_LINK" metadata::trusted true 2>/dev/null || true
fi
# Alternate trust flag some Mint versions use
chmod u+x "$DESKTOP_LINK"

update-desktop-database "$SHARE_APP" 2>/dev/null || true

echo ""
echo "============================================"
echo "  Installation complete — Desktop App ready"
echo "============================================"
echo "  Menu name : SlipNet VPN"
echo "  Desktop   : ${DESKTOP_LINK}"
echo "  Command   : slipnet-vpn"
echo ""
echo "  Fungua kutoka:"
echo "    • Menu ya Linux Mint → tafuta 'SlipNet'"
echo "    • Icon kwenye Desktop"
echo "    • Au: slipnet-vpn"
echo "============================================"
