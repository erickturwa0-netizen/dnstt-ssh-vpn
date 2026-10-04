#!/usr/bin/env python3
"""Full-system VPN GUI (Linux): DNSTT+SSH na SlipNet (slipnet://).

- Mode DNSTT+SSH: jaza fields → CONNECT
- Mode SlipNet: import slipnet:// → CONNECT
- Upload / Download live stats kuthibitisha data inapita
"""
import base64
import json
import os
import platform
import re
import shutil
import socket
import struct
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from urllib.parse import urlparse
from urllib.request import urlretrieve

CFG_DIR = os.path.expanduser("~/.config/dnstt-ssh-vpn")
BIN_DIR = os.path.join(CFG_DIR, "bin")
CFG = os.path.join(CFG_DIR, "last.json")
PROFILES = os.path.join(CFG_DIR, "profiles.json")

SOCKS_PORT_DEFAULT = "1080"
TUN = "tun0"
IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
SLIPNET_CLI_TAG = "v2.5.3"
SLIPNET_CLI_BASE = f"https://github.com/anonvector/SlipNet/releases/download/{SLIPNET_CLI_TAG}"

DNSTT_FIELDS = [
    ("mode", "Mode (udp/doh/dot)", "udp"),
    ("resolver", "Dns resolve", "8.8.8.8:53"),
    ("domain", "NS (Tunnel domain)", ""),
    ("pubkey", "PUBLIC KEY", ""),
    ("ssh_host", "SSH HOST", "127.0.0.1"),
    ("ssh_port", "SSH PORT", "7000"),
    ("ssh_user", "USERNAME", ""),
    ("ssh_pass", "PASSWORD", ""),
    ("dns_up", "DNS upstream", "8.8.8.8"),
    ("socks_port", "SOCKS port", SOCKS_PORT_DEFAULT),
]

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
    s.sendall(b"\x05\x01\x00")
    s.recv(2)
    s.sendall(b"\x05\x01\x00\x01" + socket.inet_aton(host) + struct.pack(">H", hport))
    r = s.recv(10)
    if len(r) < 2 or r[1] != 0:
        raise OSError("socks fail")
    return s


def goarch():
    m = platform.machine().lower()
    if m in ("x86_64", "amd64"):
        return "amd64"
    if m in ("aarch64", "arm64"):
        return "arm64"
    if m.startswith("arm"):
        return "armv7"
    return m


def find_binary(name):
    p = shutil.which(name)
    if p:
        return p
    for d in ("/usr/local/bin", "/usr/bin", BIN_DIR, os.path.expanduser("~/Apps/dnstt-ssh-vpn")):
        cand = os.path.join(d, name)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def ensure_binary(name, log_fn):
    """Find or download known binaries once."""
    found = find_binary(name)
    if found:
        return found
    os.makedirs(BIN_DIR, exist_ok=True)
    arch = goarch()

    try:
        if name == "tun2socks":
            log_fn("Inapakua tun2socks...")
            zname = f"tun2socks-linux-{'amd64' if arch == 'amd64' else 'arm64'}.zip"
            url = f"https://github.com/xjasonlyu/tun2socks/releases/latest/download/{zname}"
            zpath = os.path.join(BIN_DIR, zname)
            urlretrieve(url, zpath)
            import zipfile

            with zipfile.ZipFile(zpath, "r") as z:
                z.extractall(BIN_DIR)
            os.remove(zpath)
            for fn in os.listdir(BIN_DIR):
                if fn.startswith("tun2socks") and not fn.endswith(".zip"):
                    src = os.path.join(BIN_DIR, fn)
                    dest = os.path.join(BIN_DIR, "tun2socks")
                    if src != dest:
                        shutil.move(src, dest)
                    os.chmod(dest, 0o755)
                    return dest

        if name == "dnstt-client":
            log_fn("Inapakua dnstt-client...")
            url = f"https://github.com/net2share/dnstt/releases/latest/download/dnstt-client-linux-{arch if arch != 'armv7' else 'arm64'}"
            dest = os.path.join(BIN_DIR, "dnstt-client")
            urlretrieve(url, dest)
            os.chmod(dest, 0o755)
            return dest

        if name == "slipnet":
            log_fn("Inapakua slipnet CLI...")
            url = f"{SLIPNET_CLI_BASE}/slipnet-linux-{arch}"
            dest = os.path.join(BIN_DIR, "slipnet")
            urlretrieve(url, dest)
            os.chmod(dest, 0o755)
            return dest
    except Exception as e:
        log_fn(f"Download {name} fail: {e}")
    return None


def parse_slipnet_uri(text):
    text = text.strip()
    if not text:
        raise ValueError("Config tupu")
    if text.startswith("slipnet-enc://") or text.startswith("slipnet-bundle-enc://"):
        raise ValueError("Encrypted slipnet-enc:// haitumiki hapa. Tumia slipnet://.")

    if text.startswith("slipnet://"):
        b64 = text[len("slipnet://") :].strip()
        raw_uri = text
    elif re.match(r"^[A-Za-z0-9+/=\-_]+$", text) and len(text) > 40:
        b64 = text
        raw_uri = "slipnet://" + text
    else:
        raise ValueError("Si slipnet:// URI")

    pad = "=" * ((4 - len(b64) % 4) % 4)
    decoded = base64.b64decode(b64 + pad).decode("utf-8", errors="replace")
    fields = decoded.split("|")
    if len(fields) < 5:
        raise ValueError("Profile fupi mno")

    resolvers = fields[4] if len(fields) > 4 else ""
    resolver_host = "8.8.8.8"
    if resolvers:
        resolver_host = resolvers.split(",")[0].split(":")[0] or "8.8.8.8"
    socks = fields[8] if len(fields) > 8 else SOCKS_PORT_DEFAULT
    try:
        socks = int(socks) if str(socks).isdigit() else int(SOCKS_PORT_DEFAULT)
    except Exception:
        socks = int(SOCKS_PORT_DEFAULT)

    return {
        "uri": raw_uri if raw_uri.startswith("slipnet://") else "slipnet://" + b64,
        "version": fields[0],
        "tunnel_type": fields[1] if len(fields) > 1 else "",
        "name": fields[2] if len(fields) > 2 else "",
        "domain": fields[3] if len(fields) > 3 else "",
        "resolvers": resolvers,
        "resolver_host": resolver_host,
        "pubkey": fields[11] if len(fields) > 11 else "",
        "socks_port": socks,
    }


def read_tun_bytes():
    """RX/TX bytes on TUN device (kernel counters)."""
    path = f"/sys/class/net/{TUN}/statistics"
    try:
        with open(f"{path}/rx_bytes") as f:
            rx = int(f.read().strip())
        with open(f"{path}/tx_bytes") as f:
            tx = int(f.read().strip())
        return rx, tx
    except Exception:
        return None, None


def fmt_rate(bps):
    if bps < 1024:
        return f"{bps:.0f} B/s"
    if bps < 1024 * 1024:
        return f"{bps/1024:.1f} KB/s"
    return f"{bps/1024/1024:.2f} MB/s"


def fmt_total(b):
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b/1024:.1f} KB"
    if b < 1024 * 1024 * 1024:
        return f"{b/1024/1024:.2f} MB"
    return f"{b/1024/1024/1024:.2f} GB"


class DNSProxy(threading.Thread):
    def __init__(self, socks_port, upstream):
        super().__init__(daemon=True)
        self.sp, self.up, self.stop_ev = socks_port, upstream, threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 5353))
        self.sock.settimeout(1)

    def run(self):
        while not self.stop_ev.is_set():
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self.handle, args=(data, addr), daemon=True).start()

    def handle(self, data, addr):
        try:
            s = socks_connect(self.sp, self.up, 53)
            s.sendall(struct.pack(">H", len(data)) + data)
            ln = struct.unpack(">H", s.recv(2))[0]
            buf = b""
            while len(buf) < ln:
                c = s.recv(ln - len(buf))
                if not c:
                    break
                buf += c
            s.close()
            self.sock.sendto(buf, addr)
        except Exception:
            pass

    def close(self):
        self.stop_ev.set()
        try:
            self.sock.close()
        except Exception:
            pass


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SlipNet / DNSTT VPN")
        self.geometry("640x860")
        self.procs, self.dns, self.res_ip, self.up = [], None, None, False
        self._stats_stop = threading.Event()
        self._rx0 = self._tx0 = 0
        self._last_rx = self._last_tx = 0
        self._last_t = time.time()

        cfg = load_json(CFG, {})
        self.profiles = load_json(PROFILES, {})
        self.slipnet_cfg = cfg.get("slipnet") or {}
        self.vars = {}

        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)

        # Mode selector
        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Mode:").pack(side="left")
        self.app_mode = tk.StringVar(value=cfg.get("app_mode", "dnstt"))
        ttk.Radiobutton(
            top, text="DNSTT + SSH", variable=self.app_mode, value="dnstt", command=self._switch_mode
        ).pack(side="left", padx=8)
        ttk.Radiobutton(
            top, text="SlipNet (slipnet://)", variable=self.app_mode, value="slipnet", command=self._switch_mode
        ).pack(side="left", padx=8)

        # ---- DNSTT panel ----
        self.dnstt_frame = ttk.LabelFrame(outer, text="DNSTT + SSH settings", padding=6)
        for i, (k, label, d) in enumerate(DNSTT_FIELDS):
            ttk.Label(self.dnstt_frame, text=label).grid(row=i, column=0, sticky="w", pady=1, padx=(0, 6))
            v = tk.StringVar(value=cfg.get(k, d))
            self.vars[k] = v
            show = "*" if k == "ssh_pass" else ""
            ttk.Entry(self.dnstt_frame, textvariable=v, width=42, show=show).grid(
                row=i, column=1, sticky="ew", pady=1
            )
        self.dnstt_frame.columnconfigure(1, weight=1)

        # ---- SlipNet panel ----
        self.slip_frame = ttk.LabelFrame(outer, text="SlipNet import (slipnet://)", padding=6)
        self.import_box = scrolledtext.ScrolledText(self.slip_frame, height=3, wrap="word")
        self.import_box.pack(fill="x", pady=2)
        if self.slipnet_cfg.get("uri"):
            self.import_box.insert("1.0", self.slipnet_cfg["uri"])
        ttk.Button(self.slip_frame, text="IMPORT CONFIG", command=self.do_import_slipnet).pack(
            fill="x", pady=2
        )
        self.slip_info = tk.StringVar(value=self._slip_info_text())
        ttk.Label(self.slip_frame, textvariable=self.slip_info, justify="left").pack(anchor="w")

        # Connect + stats
        self.btn = ttk.Button(outer, text="CONNECT VPN", command=self.toggle)
        self.btn.pack(fill="x", pady=6)
        self.status = ttk.Label(outer, text="Disconnected", foreground="red")
        self.status.pack()

        stats = ttk.LabelFrame(outer, text="Traffic (thibitisha internet)", padding=6)
        stats.pack(fill="x", pady=4)
        self.down_var = tk.StringVar(value="↓ Download: —")
        self.up_var = tk.StringVar(value="↑ Upload: —")
        self.total_var = tk.StringVar(value="Total: —")
        ttk.Label(stats, textvariable=self.down_var, foreground="#0a7").pack(anchor="w")
        ttk.Label(stats, textvariable=self.up_var, foreground="#07a").pack(anchor="w")
        ttk.Label(stats, textvariable=self.total_var).pack(anchor="w")

        self.log = tk.Text(outer, height=8, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, pady=4)

        # Profiles
        pf = ttk.LabelFrame(outer, text="Profiles", padding=4)
        pf.pack(fill="x")
        r0 = ttk.Frame(pf)
        r0.pack(fill="x")
        ttk.Label(r0, text="PROFILE NAME").pack(side="left")
        self.profile_name = tk.StringVar()
        ttk.Entry(r0, textvariable=self.profile_name, width=22).pack(
            side="left", padx=6, fill="x", expand=True
        )
        r1 = ttk.Frame(pf)
        r1.pack(fill="x", pady=2)
        self.profile_combo = ttk.Combobox(r1, state="readonly", width=20)
        self.profile_combo.pack(side="left", padx=(0, 4))
        ttk.Button(r1, text="Load", command=self.load_profile).pack(side="left", padx=2)
        ttk.Button(r1, text="Delete", command=self.delete_profile).pack(side="left", padx=2)
        ttk.Button(pf, text="SAVE PROFILE", command=self.save_profile).pack(fill="x", pady=2)

        self.refresh_profiles()
        self._switch_mode()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _slip_info_text(self):
        d = self.slipnet_cfg
        if not d.get("uri"):
            return "Hakuna SlipNet config. Bandika slipnet:// → IMPORT."
        return (
            f"Name: {d.get('name', '-')} | Type: {d.get('tunnel_type', '-')}\n"
            f"Domain: {d.get('domain', '-')} | Resolvers: {d.get('resolvers', '-')}"
        )

    def _switch_mode(self):
        if self.app_mode.get() == "slipnet":
            self.dnstt_frame.pack_forget()
            self.slip_frame.pack(fill="x", pady=(0, 4), after=self.btn.master.winfo_children()[0])
            # pack order: after mode selector
            children = [c for c in self.winfo_children()[0].winfo_children()]
            self.slip_frame.pack(fill="x", pady=(0, 4))
            self.dnstt_frame.pack_forget()
        else:
            self.slip_frame.pack_forget()
            self.dnstt_frame.pack(fill="x", pady=(0, 4))

        # re-pack connect after panels
        self.btn.pack_forget()
        self.status.pack_forget()
        for w in (self.btn, self.status):
            pass
        # simpler: just ensure frames visibility
        if self.app_mode.get() == "dnstt":
            self.dnstt_frame.pack(fill="x", pady=(0, 4))
            self.slip_frame.pack_forget()
        else:
            self.slip_frame.pack(fill="x", pady=(0, 4))
            self.dnstt_frame.pack_forget()

    def do_import_slipnet(self):
        raw = self.import_box.get("1.0", "end").strip()
        try:
            data = parse_slipnet_uri(raw)
        except Exception as e:
            return messagebox.showerror("Import", str(e))
        self.slipnet_cfg = data
        self.slip_info.set(self._slip_info_text())
        self.profile_name.set(data.get("name") or "")
        self._save_last()
        self.w(f"SlipNet imported: {data.get('tunnel_type')} / {data.get('domain')}")
        messagebox.showinfo("Import", f"OK\nType: {data.get('tunnel_type')}\nDomain: {data.get('domain')}")

    def current_dnstt(self):
        return {k: v.get().strip() for k, v in self.vars.items()}

    def _save_last(self):
        data = self.current_dnstt()
        data["app_mode"] = self.app_mode.get()
        data["slipnet"] = self.slipnet_cfg
        save_json(CFG, data)

    def refresh_profiles(self):
        names = sorted(self.profiles.keys())
        self.profile_combo["values"] = names
        if names and not self.profile_combo.get():
            self.profile_combo.set(names[0])

    def save_profile(self):
        name = self.profile_name.get().strip()
        if not name:
            return messagebox.showerror("Error", "Andika PROFILE NAME")
        payload = {
            "app_mode": self.app_mode.get(),
            "dnstt": self.current_dnstt(),
            "slipnet": self.slipnet_cfg,
            "uri_raw": self.import_box.get("1.0", "end").strip(),
        }
        self.profiles[name] = payload
        save_json(PROFILES, self.profiles)
        self._save_last()
        self.refresh_profiles()
        self.profile_combo.set(name)
        messagebox.showinfo("Saved", f"Profile '{name}' imehifadhiwa.")

    def load_profile(self):
        name = self.profile_combo.get()
        if not name or name not in self.profiles:
            return messagebox.showerror("Error", "Chagua profile")
        p = self.profiles[name]
        self.app_mode.set(p.get("app_mode", "dnstt"))
        for k, v in (p.get("dnstt") or {}).items():
            if k in self.vars:
                self.vars[k].set(str(v))
        self.slipnet_cfg = p.get("slipnet") or {}
        self.import_box.delete("1.0", "end")
        self.import_box.insert("1.0", p.get("uri_raw") or self.slipnet_cfg.get("uri", ""))
        self.slip_info.set(self._slip_info_text())
        self.profile_name.set(name)
        self._switch_mode()
        self._save_last()
        self.w(f"Loaded profile: {name}")

    def delete_profile(self):
        name = self.profile_combo.get()
        if not name or name not in self.profiles:
            return
        if not messagebox.askyesno("Delete", f"Futa '{name}'?"):
            return
        del self.profiles[name]
        save_json(PROFILES, self.profiles)
        self.refresh_profiles()

    def w(self, m):
        self.log.config(state="normal")
        self.log.insert("end", m + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def toggle(self):
        if self.up:
            self.stop()
        else:
            threading.Thread(target=self.start, daemon=True).start()

    def ui(self, fn, *a):
        self.after(0, fn, *a)

    def start(self):
        mode = self.app_mode.get()
        self._save_last()

        if mode == "slipnet":
            self._start_slipnet()
        else:
            self._start_dnstt()

    def _start_slipnet(self):
        if not self.slipnet_cfg.get("uri"):
            # try import box
            raw = self.import_box.get("1.0", "end").strip()
            if raw:
                try:
                    self.slipnet_cfg = parse_slipnet_uri(raw)
                    self.ui(self.slip_info.set, self._slip_info_text())
                except Exception as e:
                    return self.ui(messagebox.showerror, "Error", str(e))
            else:
                return self.ui(messagebox.showerror, "Error", "Import slipnet:// config kwanza")

        uri = self.slipnet_cfg["uri"]
        socks_port = int(self.slipnet_cfg.get("socks_port") or SOCKS_PORT_DEFAULT)
        resolver_host = self.slipnet_cfg.get("resolver_host") or "8.8.8.8"

        self.ui(self.w, "SlipNet mode — binaries...")
        sn = ensure_binary("slipnet", lambda m: self.ui(self.w, m))
        t2s = ensure_binary("tun2socks", lambda m: self.ui(self.w, m))
        if not sn or not t2s:
            return self.ui(messagebox.showerror, "Error", "slipnet / tun2socks haipatikani")

        try:
            self.res_ip = socket.gethostbyname(resolver_host)
        except Exception:
            self.res_ip = "8.8.8.8"

        self.up = True
        self.ui(self.btn.config, {"text": "DISCONNECT"})
        self.ui(self.w, f"1/3 slipnet → SOCKS :{socks_port}")
        self.spawn([sn, "--port", str(socks_port), uri], "slipnet")

        if not self._wait_port(socks_port, 60):
            self.ui(self.w, "SOCKS haikufunguka")
            return self.stop()

        self._finish_tunnel(t2s, socks_port, "8.8.8.8")

    def _start_dnstt(self):
        g = self.current_dnstt()
        if not g["domain"] or not g["pubkey"]:
            return self.ui(messagebox.showerror, "Error", "NS na PUBLIC KEY zinahitajika")
        if not g["ssh_user"]:
            return self.ui(messagebox.showerror, "Error", "USERNAME inahitajika")

        self.ui(self.w, "DNSTT+SSH mode — binaries...")
        dnstt = ensure_binary("dnstt-client", lambda m: self.ui(self.w, m))
        t2s = ensure_binary("tun2socks", lambda m: self.ui(self.w, m))
        if not dnstt or not t2s:
            return self.ui(messagebox.showerror, "Error", "dnstt-client / tun2socks haipatikani")

        host = (
            urlparse(g["resolver"]).hostname
            if "://" in g["resolver"]
            else g["resolver"].rsplit(":", 1)[0]
        )
        try:
            self.res_ip = socket.gethostbyname(host)
        except Exception:
            return self.ui(messagebox.showerror, "Error", "Dns resolve haijulikani")

        flag = {"udp": "-udp", "doh": "-doh", "dot": "-dot"}.get(g["mode"].lower(), "-udp")
        key = (
            ["-pubkey-file", g["pubkey"]]
            if os.path.isfile(g["pubkey"])
            else ["-pubkey", g["pubkey"]]
        )
        local_port = g["ssh_port"] or "7000"
        socks_port = int(g.get("socks_port") or SOCKS_PORT_DEFAULT)
        ssh_target = g["ssh_host"] or "127.0.0.1"

        self.up = True
        self.ui(self.btn.config, {"text": "DISCONNECT"})
        self.ui(self.w, "1/4 DNSTT...")
        self.spawn(
            [dnstt, flag, g["resolver"], *key, g["domain"], f"127.0.0.1:{local_port}"],
            "dnstt",
        )
        time.sleep(2)

        self.ui(self.w, "2/4 SSH...")
        ssh = [
            "ssh",
            "-N",
            "-D",
            f"127.0.0.1:{socks_port}",
            "-p",
            local_port,
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ExitOnForwardFailure=yes",
            f"{g['ssh_user']}@{ssh_target}",
        ]
        env = os.environ.copy()
        if g["ssh_pass"]:
            env["SSHPASS"] = g["ssh_pass"]
            ssh = ["sshpass", "-e"] + ssh
        self.spawn(ssh, "ssh", env)

        if not self._wait_port(socks_port, 45):
            self.ui(self.w, "SSH SOCKS haikufunguka")
            return self.stop()

        self._finish_tunnel(t2s, socks_port, g.get("dns_up") or "8.8.8.8")

    def _wait_port(self, port, tries):
        for _ in range(tries):
            if not self.up:
                return False
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                return True
            except OSError:
                time.sleep(1)
        return False

    def _finish_tunnel(self, t2s, socks_port, dns_up):
        self.ui(self.w, "3/4 DNS proxy + tun2socks...")
        self.dns = DNSProxy(socks_port, dns_up)
        self.dns.start()
        self.spawn(
            [t2s, "-device", f"tun://{TUN}", "-proxy", f"socks5://127.0.0.1:{socks_port}"],
            "tun2socks",
        )
        self.ui(self.w, "4/4 Routes (pkexec)...")
        r = pk(UP % {"tun": TUN, "res": self.res_ip})
        if r.returncode != 0:
            self.ui(self.w, "Routes fail: " + (r.stderr or r.stdout))
            return self.stop()

        self.ui(self.status.config, {"text": "VPN ON", "foreground": "green"})
        self._start_stats()
        # optional connectivity probe
        threading.Thread(target=self._probe_internet, daemon=True).start()
        self.watch()

    def _probe_internet(self):
        time.sleep(2)
        try:
            # through system stack (should use tunnel if routes OK)
            import urllib.request

            with urllib.request.urlopen("https://httpbin.org/ip", timeout=15) as r:
                body = r.read().decode()[:200]
            self.ui(self.w, f"Internet OK via tunnel: {body.strip()}")
        except Exception as e:
            self.ui(self.w, f"Probe: bado hakuna internet wazi ({e})")

    def _start_stats(self):
        self._stats_stop.clear()
        rx, tx = read_tun_bytes()
        self._rx0 = rx or 0
        self._tx0 = tx or 0
        self._last_rx = self._rx0
        self._last_tx = self._tx0
        self._last_t = time.time()

        def loop():
            while not self._stats_stop.is_set() and self.up:
                time.sleep(1)
                rx, tx = read_tun_bytes()
                if rx is None:
                    continue
                now = time.time()
                dt = max(now - self._last_t, 0.001)
                down_rate = (rx - self._last_rx) / dt  # RX on tun = download from net perspective via tunnel
                up_rate = (tx - self._last_tx) / dt
                self._last_rx, self._last_tx, self._last_t = rx, tx, now
                total_down = rx - self._rx0
                total_up = tx - self._tx0
                self.ui(
                    self.down_var.set,
                    f"↓ Download: {fmt_rate(down_rate)}  ({fmt_total(total_down)})",
                )
                self.ui(
                    self.up_var.set,
                    f"↑ Upload: {fmt_rate(up_rate)}  ({fmt_total(total_up)})",
                )
                self.ui(
                    self.total_var.set,
                    f"Total: ↓ {fmt_total(total_down)}  ↑ {fmt_total(total_up)}",
                )

        threading.Thread(target=loop, daemon=True).start()

    def spawn(self, cmd, name, env=None):
        p = subprocess.Popen(
            cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        self.procs.append(p)

        def rd():
            for line in p.stdout:
                self.ui(self.w, f"[{name}] {line.rstrip()}")

        threading.Thread(target=rd, daemon=True).start()

    def watch(self):
        while self.up:
            time.sleep(2)
            if any(p.poll() is not None for p in self.procs):
                self.ui(self.w, "Process imesimama — nazima VPN.")
                self.stop()
                break

    def stop(self):
        if not self.up and not self.procs:
            return
        self.up = False
        self._stats_stop.set()
        for p in reversed(self.procs):
            try:
                p.terminate()
            except Exception:
                pass
        self.procs = []
        if self.dns:
            self.dns.close()
            self.dns = None
        if self.res_ip:
            pk(DOWN % {"tun": TUN, "res": self.res_ip})
        self.ui(self.btn.config, {"text": "CONNECT VPN"})
        self.ui(self.status.config, {"text": "Disconnected", "foreground": "red"})
        self.ui(self.down_var.set, "↓ Download: —")
        self.ui(self.up_var.set, "↑ Upload: —")
        self.ui(self.total_var.set, "Total: —")

    def on_close(self):
        self.stop()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
