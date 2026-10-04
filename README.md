# DNSTT + SSH Full-System VPN (Linux GUI)

Python/Tkinter GUI that builds a **full-system VPN** on Linux by chaining:

1. **dnstt-client** — DNS tunnel (UDP / DoH / DoT)
2. **SSH** dynamic SOCKS5 proxy over the tunnel
3. **tun2socks** — TUN device that routes all traffic through the SOCKS proxy
4. Policy routing + `resolvectl` so DNS and default route go via the tunnel

All traffic (including DNS) is forced through the tunnel. The app runs as a normal user and only uses `pkexec` for the privileged route/TUN setup.

## Requirements

### System packages
```bash
sudo apt install python3-tk openssh-client sshpass iproute2 policykit-1 systemd-resolved
# or equivalent on your distro
```

### Binaries (must be in `$PATH` or give full path in the GUI)
- [dnstt-client](https://github.com/aalto-speech/dnstt) (or your fork)
- [tun2socks](https://github.com/xjasonlyu/tun2socks)

## Usage

```bash
python3 dnstt_ssh_vpn.py
```

### Connection fields

| Field | Description |
|-------|-------------|
| dnstt-client path | Path or name of `dnstt-client` |
| tun2socks path | Path or name of `tun2socks` |
| Mode | `udp`, `doh`, or `dot` |
| **Dns resolve** | e.g. `8.8.8.8:53` or DoH URL |
| **NS** | Tunnel domain |
| **PUBLIC KEY** | Hex pubkey or path to `.pub` file |
| **SSH HOST** | Usually `127.0.0.1` (local end of DNSTT) |
| **SSH PORT** | Local DNSTT listen port (default `7000`) |
| **USERNAME** | SSH username on far side |
| **PASSWORD** | SSH password |
| SOCKS5 port | Default `1080` |
| **DNS** | Upstream DNS *through* the tunnel (default `8.8.8.8`) |

### Profiles (bottom of the window)

1. Fill the fields above.
2. Type a **PROFILE NAME**.
3. Click **SAVE PROFILE**.
4. Later: pick from the dropdown → **Load** (or **Delete**).

Profiles are stored in `~/.config/dnstt-ssh-vpn/profiles.json` (mode 600). Last used values also go to `last.json`.

Click **CONNECT VPN**. The app will:

1. Start dnstt-client
2. Open an SSH SOCKS proxy through the tunnel
3. Start a local DNS proxy (UDP → TCP via SOCKS) + tun2socks
4. Ask for admin password (`pkexec`) to create `tun0` and install routes

When connected, status turns green and **all traffic** goes through the tunnel.

## Notes / Limitations

- Linux only (uses `ip`, `resolvectl`, `pkexec`, TUN).
- Requires a working DNSTT server + SSH daemon reachable on the other side of the tunnel.
- DNS is forced through a small UDP→TCP proxy because SSH only carries TCP.
- Stopping the app (or any of the child processes dying) tears down routes and the TUN device.

## License

MIT (or whatever you prefer — feel free to change).
