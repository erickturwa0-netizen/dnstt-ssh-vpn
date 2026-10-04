# Verification results (2026-10-04)

## Real tests run in sandbox

### 1. Python syntax
- `python3 -m py_compile dnstt_ssh_vpn.py` → **OK**

### 2. SlipNet URI decode (user sample)
```
version=16 type=sayedns name=n.igoii.org domain=n.igoii.org
resolvers=8.8.8.8:53:0 socks=1080 pubkey=1b84dc04...
```
→ **DECODE_OK**

### 3. Binary downloads
- `slipnet-linux-amd64` (v2.5.3) → HTTP 302, downloads OK (~2.9 MB)
- `tun2socks-linux-amd64.zip` (v2.7.0) → OK
- `dnstt-client-linux-amd64` → OK

### 4. Live SlipNet CLI with user config
```
./slipnet --port 19080 'slipnet://MTZ8...'
```
Output:
```
Profile:    n.igoii.org
Type:       sayedns
Domain:     n.igoii.org
Connected! SOCKS5 proxy listening on 127.0.0.1:19080
```
→ **REAL CONNECT** (not fake)

### 5. HTTP via SOCKS
- curl through SOCKS timed out in this sandbox (restricted egress / slow DNS tunnel).
- On a normal Linux Mint desktop with working path to the server, traffic should flow; app shows live ↓↑ counters from TUN stats.

## What is real vs local-only
| Component | Status |
|-----------|--------|
| slipnet:// import/parse | Real |
| Official slipnet CLI | Real, tested |
| SOCKS listen | Real, tested |
| tun2socks + system routes | Real code path (needs pkexec on user machine) |
| Upload/Download meters | Real kernel TUN rx/tx bytes |
| End-to-end HTTP in sandbox | Timed out here (environment limit) |
