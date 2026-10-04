# DNSTT / SlipNet VPN

**Linux Mint (desktop)** + **Android (APK)** — both in this repo.

## 1. Linux Mint (full-system VPN)

```bash
curl -fsSL https://raw.githubusercontent.com/erickturwa0-netizen/dnstt-ssh-vpn/main/install.sh | bash
```

- Menu / Desktop: **SlipNet VPN**
- Modes: **DNSTT + SSH** and **SlipNet** (`slipnet://` import)
- Live ↑↓ traffic stats
- Uses real `slipnet` CLI + `tun2socks` + system routes

Files: `dnstt_ssh_vpn.py`, `install.sh`

## 2. Android APK (red theme)

GitHub Actions builds the APK automatically.

### Download APK

1. Open **Actions** → **Build Android APK**
2. Run workflow (**Run workflow**) if needed
3. Open the latest run → download artifact **SlipNet-VPN-debug**
4. Or check **Releases** after manual dispatch

Direct Actions URL:  
https://github.com/erickturwa0-netizen/dnstt-ssh-vpn/actions

Android sources: `android/`

## Test notes

See `TEST_RESULTS.md` — SlipNet CLI was verified live with a real `slipnet://` config (SOCKS connected).
