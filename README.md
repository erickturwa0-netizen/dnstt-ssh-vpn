# DNSTT + SSH Full-System VPN (Linux GUI)

Python/Tkinter GUI that builds a **full-system VPN** on Linux by chaining:

1. **dnstt-client** — DNS tunnel (UDP / DoH / DoT)
2. **SSH** dynamic SOCKS5 proxy over the tunnel
3. **tun2socks** — TUN device that routes all traffic through the SOCKS proxy
4. Policy routing + `resolvectl` so DNS and default route go via the tunnel

All traffic (including DNS) is forced through the tunnel. The app runs as a normal user and only uses `pkexec` for the privileged route/TUN setup.

## One-command install (Linux Mint / Ubuntu / Debian)

```bash
curl -fsSL https://raw.githubusercontent.com/erickturwa0-netizen/dnstt-ssh-vpn/main/install.sh | bash
```

Au:

```bash
git clone https://github.com/erickturwa0-netizen/dnstt-ssh-vpn.git
cd dnstt-ssh-vpn
chmod +x install.sh
./install.sh
```

Script itafanya:
- Install system packages (`python3-tk`, `sshpass`, `iproute2`, ...)
- Download **dnstt-client** + **tun2socks** → `/usr/local/bin/`
- Clone/update app → `~/Apps/dnstt-ssh-vpn`
- Tengeneza desktop launcher (itaonekana kwenye menu)

## Manual requirements (ikiwa hutatumi install.sh)

```bash
sudo apt install python3-tk openssh-client sshpass iproute2 policykit-1 systemd-resolved
```

Binaries:
- [dnstt-client](https://github.com/net2share/dnstt/releases) (linux-amd64 / linux-arm64)
- [tun2socks](https://github.com/xjasonlyu/tun2socks/releases) (`tun2socks-linux-amd64.zip`)

## Usage

```bash
python3 ~/Apps/dnstt-ssh-vpn/dnstt_ssh_vpn.py
```

Au fungua **DNSTT + SSH VPN** kutoka menu.

### Connection fields

| Field | Description |
|-------|-------------|
| dnstt-client path | `dnstt-client` (baada ya install.sh) |
| tun2socks path | `tun2socks` |
| Mode | `udp`, `doh`, or `dot` |
| **Dns resolve** | e.g. `8.8.8.8:53` or DoH URL |
| **NS** | Tunnel domain |
| **PUBLIC KEY** | Hex pubkey or path to `.pub` file |
| **SSH HOST** | Usually `127.0.0.1` |
| **SSH PORT** | Local DNSTT port (default `7000`) |
| **USERNAME** | SSH username |
| **PASSWORD** | SSH password |
| SOCKS5 port | Default `1080` |
| **DNS** | Upstream DNS through tunnel |

### Profiles

1. Jaza fields → andika **PROFILE NAME** → **SAVE PROFILE**
2. Baadaye: chagua kutoka dropdown → **Load**

Profiles: `~/.config/dnstt-ssh-vpn/profiles.json`

## Notes

- Linux only (`ip`, `resolvectl`, `pkexec`, TUN).
- Unahitaji DNSTT server + SSH upande wa pili.
- Disconnect au process ikifa → routes/TUN zinaondolewa.

## License

MIT
