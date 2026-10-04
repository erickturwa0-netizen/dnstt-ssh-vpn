# SlipNet VPN — Android

Red-themed Android client matching the Linux Mint GUI:

- **DNSTT + SSH** form fields
- **SlipNet** `slipnet://` import
- Profiles
- VPN permission + TUN service

## Build (GitHub Actions)

Push to `main` or run workflow **Build Android APK** → download artifact `SlipNet-VPN-debug`.

## Local build

```bash
cd android
gradle wrapper --gradle-version 8.7
./gradlew assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk
```

## Note on tunneling

Full DNSTT / NoizDNS / Slipstream engines on Android require native binaries (as in official [SlipNet](https://github.com/anonvector/SlipNet) APK).  
This app provides the **same UI + config import + Android VpnService shell**.  
Linux Mint full-system path remains in repo root (`dnstt_ssh_vpn.py` + `install.sh`).
