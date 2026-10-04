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

Fill in the fields:

| Field | Description |
|-------|-------------|
| dnstt-client path | Path or name of `dnstt-client` |
| tun2socks path | Path or name of `tun2socks` |
| Mode | `udp`, `doh`, or `dot` |
| Resolver | e.g. `8.8.8.8:53` or DoH URL |
| Tunnel domain (NS) | Your DNSTT domain |
| Pubkey | Hex pubkey or path to `.pub` file |
| SSH username / password | Credentials on the far side of the tunnel |
| Local DNSTT port | Default `7000` |
| SOCKS5 port | Default `1080` |
| DNS upstream | DNS server reached *through* the tunnel (default `8.8.8.8`) |

Click **CONNECT VPN**. The app will:

1. Start dnstt-client
2. Open an SSH SOCKS proxy through the tunnel
3. Start a local DNS proxy (UDP → TCP via SOCKS) + tun2socks
4. Ask for admin password (`pkexec`) to create `tun0` and install routes

When connected, status turns green and **all traffic** goes through the tunnel.

Config is saved to `~/.config/dnstt-ssh-vpn.json` (mode 600).

## Notes / Limitations

- Linux only (uses `ip`, `resolvectl`, `pkexec`, TUN).
- Requires a working DNSTT server + SSH daemon reachable on the other side of the tunnel.
- DNS is forced through a small UDP→TCP proxy because SSH only carries TCP.
- Stopping the app (or any of the child processes dying) tears down routes and the TUN device.

## License

MIT (or whatever you prefer — feel free to change).
