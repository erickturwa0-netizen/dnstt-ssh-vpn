#!/usr/bin/env python3
"""DNSTT + SSH full-system VPN GUI (Linux).
Inahitaji: python3-tk openssh-client sshpass iproute2 policykit-1 (pkexec) systemd-resolved
Pamoja na binaries: dnstt-client na tun2socks (xjasonlyu/tun2socks).
Endesha kama user wa kawaida; app itaomba password ya admin (pkexec) kwa routes tu.
"""
import json, os, re, shutil, socket, struct, subprocess, threading, time, tkinter as tk
from tkinter import ttk, messagebox
from urllib.parse import urlparse

CFG = os.path.expanduser("~/.config/dnstt-ssh-vpn.json")
FIELDS = [
    ("dnstt_path", "dnstt-client path", "dnstt-client"),
    ("tun2socks_path", "tun2socks path", "tun2socks"),
    ("mode", "Mode (udp/doh/dot)", "udp"),
    ("resolver", "Resolver (8.8.8.8:53 / URL ya DoH)", "8.8.8.8:53"),
    ("domain", "Tunnel domain (NS)", "t.example.com"),
    ("pubkey", "Pubkey (hex) au path ya .pub", ""),
    ("ssh_user", "SSH username", ""),
    ("ssh_pass", "SSH password", ""),
    ("dnstt_port", "Local DNSTT port", "7000"),
    ("socks_port", "SOCKS5 port", "1080"),
    ("dns_up", "DNS upstream (kupitia tunnel)", "8.8.8.8"),
]
TUN = "tun0"
IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

UP = """set -e
GW=$(ip route show default | awk '/default/ {print $3; exit}')
IF=$(ip route show default | awk '/default/ {print $5; exit}')
[ -n "$GW" ] || { echo "no default route"; exit 1; }
ip tuntap add dev %(tun)s mode tun user "$PKEXEC_UID" 2>/dev/null || true
ip addr add 198.18.0.1/15 dev %(tun)s 2>/dev/null || true
ip link set %(tun)s up
ip route replace %(res)s/32 via "$GW" dev "$IF"
ip route replace 0.0.0.0/1 dev %(tun)s
ip route replace 128.0.0.0/1 dev %(tun)s
resolvectl dns %(tun)s 127.0.0.1:5353 || true
resolvectl domain %(tun)s '~.' || true
"""
DOWN = """ip route del 0.0.0.0/1 2>/dev/null
ip route del 128.0.0.0/1 2>/dev/null
ip route del %(res)s/32 2>/dev/null
resolvectl revert %(tun)s 2>/dev/null
ip link del %(tun)s 2>/dev/null
true
"""

def pk(script):
    return subprocess.run(["pkexec", "sh", "-c", script], capture_output=True, text=True)

def socks_connect(port, host, hport):
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.sendall(b"\x05\x01\x00"); s.recv(2)
    s.sendall(b"\x05\x01\x00\x01" + socket.inet_aton(host) + struct.pack(">H", hport))
    r = s.recv(10)
    if len(r) < 2 or r[1] != 0: raise OSError("socks fail")
    return s

class DNSProxy(threading.Thread):
    """UDP DNS (127.0.0.1:5353) -> TCP DNS kupitia SOCKS (SSH ina-support TCP tu)."""
    def __init__(self, socks_port, upstream):
        super().__init__(daemon=True)
        self.sp, self.up, self.stop_ev = socks_port, upstream, threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 5353)); self.sock.settimeout(1)

    def run(self):
        while not self.stop_ev.is_set():
            try: data, addr = self.sock.recvfrom(4096)
            except socket.timeout: continue
            except OSError: break
            threading.Thread(target=self.handle, args=(data, addr), daemon=True).start()

    def handle(self, data, addr):
        try:
            s = socks_connect(self.sp, self.up, 53)
            s.sendall(struct.pack(">H", len(data)) + data)
            ln = struct.unpack(">H", s.recv(2))[0]
            buf = b""
            while len(buf) < ln:
                c = s.recv(ln - len(buf))
                if not c: break
                buf += c
            s.close(); self.sock.sendto(buf, addr)
        except Exception:
            pass

    def close(self):
        self.stop_ev.set()
        try: self.sock.close()
        except Exception: pass

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DNSTT + SSH VPN"); self.geometry("580x640")
        self.procs, self.dns, self.res_ip, self.up = [], None, None, False
        try: cfg = json.load(open(CFG))
        except Exception: cfg = {}
        self.vars = {}
        f = ttk.Frame(self, padding=12); f.pack(fill="both", expand=True)
        for i, (k, label, d) in enumerate(FIELDS):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w", pady=3)
            v = tk.StringVar(value=cfg.get(k, d)); self.vars[k] = v
            ttk.Entry(f, textvariable=v, width=38, show="*" if k == "ssh_pass" else "").grid(row=i, column=1, pady=3)
        n = len(FIELDS)
        self.btn = ttk.Button(f, text="CONNECT VPN", command=self.toggle); self.btn.grid(row=n, columnspan=2, pady=8, sticky="ew")
        self.status = ttk.Label(f, text="Disconnected", foreground="red"); self.status.grid(row=n+1, columnspan=2)
        self.log = tk.Text(f, height=12, state="disabled"); self.log.grid(row=n+2, columnspan=2, sticky="nsew", pady=6)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def w(self, m):
        self.log.config(state="normal"); self.log.insert("end", m + "\n"); self.log.see("end"); self.log.config(state="disabled")

    def toggle(self):
        if self.up: self.stop()
        else: threading.Thread(target=self.start, daemon=True).start()

    def ui(self, fn, *a): self.after(0, fn, *a)

    def start(self):
        g = {k: v.get().strip() for k, v in self.vars.items()}
        for b in (g["dnstt_path"], g["tun2socks_path"]):
            if not shutil.which(b) and not os.path.isfile(b):
                return self.ui(messagebox.showerror, "Error", f"{b} haipatikani")
        os.makedirs(os.path.dirname(CFG), exist_ok=True)
        json.dump(g, open(CFG, "w")); os.chmod(CFG, 0o600)
        host = urlparse(g["resolver"]).hostname if "://" in g["resolver"] else g["resolver"].rsplit(":", 1)[0]
        try: self.res_ip = socket.gethostbyname(host)
        except Exception: return self.ui(messagebox.showerror, "Error", "Resolver haijulikani")
        if not IP_RE.match(self.res_ip): return
        flag = {"udp": "-udp", "doh": "-doh", "dot": "-dot"}.get(g["mode"], "-udp")
        key = ["-pubkey-file", g["pubkey"]] if os.path.isfile(g["pubkey"]) else ["-pubkey", g["pubkey"]]
        dn = [g["dnstt_path"], flag, g["resolver"], *key, g["domain"], f"127.0.0.1:{g['dnstt_port']}"]
        ssh = ["ssh", "-N", "-D", f"127.0.0.1:{g['socks_port']}", "-p", g["dnstt_port"],
               "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
               "-o", "ServerAliveInterval=15", "-o", "ExitOnForwardFailure=yes", f"{g['ssh_user']}@127.0.0.1"]
        env = os.environ.copy()
        if g["ssh_pass"]: env["SSHPASS"] = g["ssh_pass"]; ssh = ["sshpass", "-e"] + ssh
        self.up = True
        self.ui(self.btn.config, {"text": "DISCONNECT"})
        self.ui(self.w, "1/4 DNSTT...")
        self.spawn(dn, "dnstt"); time.sleep(2)
        self.ui(self.w, "2/4 SSH...")
        self.spawn(ssh, "ssh", env)
        sp = int(g["socks_port"])
        for _ in range(40):
            try: socket.create_connection(("127.0.0.1", sp), timeout=1).close(); break
            except OSError: time.sleep(1)
        else:
            self.ui(self.w, "SSH haikuunganika. Angalia logs."); return self.stop()
        self.ui(self.w, "3/4 DNS proxy + tun2socks...")
        self.dns = DNSProxy(sp, g["dns_up"]); self.dns.start()
        self.spawn([g["tun2socks_path"], "-device", f"tun://{TUN}", "-proxy", f"socks5://127.0.0.1:{sp}"], "tun2socks")
        self.ui(self.w, "4/4 Routes (pkexec)...")
        r = pk(UP % {"tun": TUN, "res": self.res_ip})
        if r.returncode != 0:
            self.ui(self.w, "Routes zimeshindwa: " + (r.stderr or r.stdout)); return self.stop()
        self.ui(self.status.config, {"text": "VPN ON - trafiki yote inapita tunnel", "foreground": "green"})
        self.watch()

    def spawn(self, cmd, name, env=None):
        p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.procs.append(p)
        def rd():
            for line in p.stdout: self.ui(self.w, f"[{name}] {line.rstrip()}")
        threading.Thread(target=rd, daemon=True).start()

    def watch(self):
        while self.up:
            time.sleep(2)
            if any(p.poll() is not None for p in self.procs):
                self.ui(self.w, "Process imesimama, nazima VPN."); self.stop(); break

    def stop(self):
        if not self.up and not self.procs: return
        self.up = False
        for p in reversed(self.procs):
            try: p.terminate()
            except Exception: pass
        self.procs = []
        if self.dns: self.dns.close(); self.dns = None
        if self.res_ip: pk(DOWN % {"tun": TUN, "res": self.res_ip})
        self.ui(self.btn.config, {"text": "CONNECT VPN"})
        self.ui(self.status.config, {"text": "Disconnected", "foreground": "red"})

    def on_close(self):
        self.stop(); self.destroy()

if __name__ == "__main__":
    App().mainloop()
