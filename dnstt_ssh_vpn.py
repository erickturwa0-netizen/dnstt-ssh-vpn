#!/usr/bin/env python3
"""SlipNet + DNSTT/SSH full-system VPN GUI (Linux).

Import slipnet:// configs (anonvector/SlipNet) → CONNECT → full system VPN.
Uses official slipnet CLI (SOCKS5) + tun2socks for system-wide routing.
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

SOCKS_PORT = 1080
TUN = "tun0"
IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

# Official SlipNet CLI (has linux binaries on v2.5.3)
SLIPNET_CLI_TAG = "v2.5.3"
SLIPNET_CLI_BASE = f"https://github.com/anonvector/SlipNet/releases/download/{SLIPNET_CLI_TAG}"

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
    if m in ("armv7l", "armv7"):
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


def ensure_tun2socks(log_fn):
    t2s = find_binary("tun2socks")
    if t2s:
        return t2s
    os.makedirs(BIN_DIR, exist_ok=True)
    arch = goarch()
    if arch == "armv7":
        arch = "386"  # fallback naming; may fail on pure armv7
    log_fn("Inapakua tun2socks...")
    zip_name = f"tun2socks-linux-{arch if arch != 'armv7' else 'arm64'}.zip"
    if goarch() == "amd64":
        zip_name = "tun2socks-linux-amd64.zip"
    elif goarch() == "arm64":
        zip_name = "tun2socks-linux-arm64.zip"
    else:
        zip_name = "tun2socks-linux-amd64.zip"
    url = f"https://github.com/xjasonlyu/tun2socks/releases/latest/download/{zip_name}"
    zip_path = os.path.join(BIN_DIR, zip_name)
    try:
        urlretrieve(url, zip_path)
        import zipfile

        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(BIN_DIR)
        os.remove(zip_path)
        for fn in os.listdir(BIN_DIR):
            if fn.startswith("tun2socks") and not fn.endswith(".zip"):
                src = os.path.join(BIN_DIR, fn)
                dest = os.path.join(BIN_DIR, "tun2socks")
                if src != dest:
                    shutil.move(src, dest)
                os.chmod(dest, 0o755)
                return dest
    except Exception as e:
        log_fn(f"tun2socks fail: {e}")
    return None


def ensure_slipnet(log_fn):
    sn = find_binary("slipnet")
    if sn:
        return sn
    os.makedirs(BIN_DIR, exist_ok=True)
    arch = goarch()
    name = f"slipnet-linux-{arch}"
    url = f"{SLIPNET_CLI_BASE}/{name}"
    dest = os.path.join(BIN_DIR, "slipnet")
    log_fn(f"Inapakua slipnet CLI ({arch})...")
    try:
        urlretrieve(url, dest)
        os.chmod(dest, 0o755)
        log_fn(f"slipnet: {dest}")
        return dest
    except Exception as e:
        log_fn(f"slipnet download fail: {e}")
        return None


def parse_slipnet_uri(text):
    """Decode slipnet:// base64 pipe profile. Returns dict."""
    text = text.strip()
    if not text:
        raise ValueError("Config tupu")

    raw_uri = text
    if text.startswith("slipnet-enc://") or text.startswith("slipnet-bundle-enc://"):
        raise ValueError(
            "slipnet-enc:// / bundle-enc:// zinahitaji app ya SlipNet (encrypted).\n"
            "Tumia slipnet:// ya kawaida (isiyo encrypted)."
        )

    if text.startswith("slipnet://"):
        b64 = text[len("slipnet://") :].strip()
    elif re.match(r"^[A-Za-z0-9+/=\-_]+$", text) and len(text) > 40:
        b64 = text
        raw_uri = "slipnet://" + text
    else:
        raise ValueError("Si slipnet:// URI")

    pad = "=" * ((4 - len(b64) % 4) % 4)
    try:
        decoded = base64.b64decode(b64 + pad).decode("utf-8", errors="replace")
    except Exception as e:
        raise ValueError(f"Base64 batili: {e}") from e

    fields = decoded.split("|")
    if len(fields) < 5:
        raise ValueError("Profile fupi mno baada ya decode")

    # Format (v16+): version|tunnelType|name|domain|resolvers|...|pubkey@11|...
    version = fields[0]
    tunnel = fields[1] if len(fields) > 1 else ""
    name = fields[2] if len(fields) > 2 else ""
    domain = fields[3] if len(fields) > 3 else ""
    resolvers = fields[4] if len(fields) > 4 else ""
    # first resolver host for routing exception
    resolver_host = "8.8.8.8"
    if resolvers:
        part = resolvers.split(",")[0]
        resolver_host = part.split(":")[0] or "8.8.8.8"
    pubkey = fields[11] if len(fields) > 11 else ""
    socks_port = fields[8] if len(fields) > 8 else str(SOCKS_PORT)
    try:
        socks_port = int(socks_port) if socks_port.isdigit() else SOCKS_PORT
    except Exception:
        socks_port = SOCKS_PORT

    return {
        "uri": raw_uri if raw_uri.startswith("slipnet://") else "slipnet://" + b64,
        "version": version,
        "tunnel_type": tunnel,
        "name": name or domain or "slipnet",
        "domain": domain,
        "resolvers": resolvers,
        "resolver_host": resolver_host,
        "pubkey": pubkey,
        "socks_port": socks_port,
        "decoded": decoded,
    }


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
    os.chmod(path, 0o600)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SlipNet Full-System VPN (Linux)")
        self.geometry("640x720")
        self.procs, self.dns, self.res_ip, self.up = [], None, None, False
        self.current = load_json(CFG, {})
        self.profiles = load_json(PROFILES, {})

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        # Import
        imp = ttk.LabelFrame(outer, text="Import SlipNet config (slipnet://)", padding=8)
        imp.pack(fill="x", pady=(0, 8))
        self.import_box = scrolledtext.ScrolledText(imp, height=4, wrap="word")
        self.import_box.pack(fill="x", pady=2)
        if self.current.get("uri"):
            self.import_box.insert("1.0", self.current["uri"])
        ttk.Button(imp, text="IMPORT CONFIG", command=self.do_import).pack(fill="x", pady=4)

        # Info
        info = ttk.LabelFrame(outer, text="Profile info", padding=8)
        info.pack(fill="x", pady=(0, 8))
        self.info_var = tk.StringVar(value=self._info_text(self.current))
        ttk.Label(info, textvariable=self.info_var, justify="left").pack(anchor="w")

        # DNS override (optional)
        row = ttk.Frame(outer)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="DNS resolver (optional override)").pack(side="left")
        self.dns_override = tk.StringVar(value=self.current.get("dns_override", ""))
        ttk.Entry(row, textvariable=self.dns_override, width=28).pack(side="left", padx=8)

        self.btn = ttk.Button(outer, text="CONNECT VPN", command=self.toggle)
        self.btn.pack(fill="x", pady=8)
        self.status = ttk.Label(outer, text="Disconnected", foreground="red")
        self.status.pack()

        self.log = tk.Text(outer, height=12, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, pady=6)

        # Profiles
        pf = ttk.LabelFrame(outer, text="Profiles", padding=6)
        pf.pack(fill="x")
        r0 = ttk.Frame(pf)
        r0.pack(fill="x", pady=2)
        ttk.Label(r0, text="PROFILE NAME").pack(side="left")
        self.profile_name = tk.StringVar(value=self.current.get("name", ""))
        ttk.Entry(r0, textvariable=self.profile_name, width=24).pack(
            side="left", padx=6, fill="x", expand=True
        )
        r1 = ttk.Frame(pf)
        r1.pack(fill="x", pady=2)
        self.profile_combo = ttk.Combobox(r1, state="readonly", width=22)
        self.profile_combo.pack(side="left", padx=(0, 6))
        ttk.Button(r1, text="Load", command=self.load_profile).pack(side="left", padx=2)
        ttk.Button(r1, text="Delete", command=self.delete_profile).pack(side="left", padx=2)
        ttk.Button(pf, text="SAVE PROFILE", command=self.save_profile).pack(fill="x", pady=4)

        self.refresh_profiles()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _info_text(self, d):
        if not d or not d.get("uri"):
            return "Hakuna config. Bandika slipnet:// hapo juu → IMPORT."
        return (
            f"Name: {d.get('name', '-')}\n"
            f"Type: {d.get('tunnel_type', '-')}\n"
            f"Domain: {d.get('domain', '-')}\n"
            f"Resolvers: {d.get('resolvers', '-')}\n"
            f"SOCKS port: {d.get('socks_port', SOCKS_PORT)}"
        )

    def do_import(self):
        raw = self.import_box.get("1.0", "end").strip()
        try:
            data = parse_slipnet_uri(raw)
        except Exception as e:
            return messagebox.showerror("Import", str(e))
        data["dns_override"] = self.dns_override.get().strip()
        self.current = data
        save_json(CFG, data)
        self.info_var.set(self._info_text(data))
        self.profile_name.set(data.get("name") or "")
        self.w(
            f"Imported OK — type={data.get('tunnel_type')} domain={data.get('domain')}"
        )
        messagebox.showinfo(
            "Import",
            f"Config imewekwa.\nType: {data.get('tunnel_type')}\nDomain: {data.get('domain')}\n\nBonyeza CONNECT VPN.",
        )

    def refresh_profiles(self):
        names = sorted(self.profiles.keys())
        self.profile_combo["values"] = names
        if names and not self.profile_combo.get():
            self.profile_combo.set(names[0])

    def save_profile(self):
        name = self.profile_name.get().strip()
        if not name:
            return messagebox.showerror("Error", "Andika PROFILE NAME")
        if not self.current.get("uri"):
            return messagebox.showerror("Error", "Import config kwanza")
        self.current["name"] = name
        self.current["dns_override"] = self.dns_override.get().strip()
        self.profiles[name] = dict(self.current)
        save_json(PROFILES, self.profiles)
        save_json(CFG, self.current)
        self.refresh_profiles()
        self.profile_combo.set(name)
        messagebox.showinfo("Saved", f"Profile '{name}' imehifadhiwa.")

    def load_profile(self):
        name = self.profile_combo.get()
        if not name or name not in self.profiles:
            return messagebox.showerror("Error", "Chagua profile")
        self.current = dict(self.profiles[name])
        self.import_box.delete("1.0", "end")
        self.import_box.insert("1.0", self.current.get("uri", ""))
        self.dns_override.set(self.current.get("dns_override", ""))
        self.profile_name.set(name)
        self.info_var.set(self._info_text(self.current))
        save_json(CFG, self.current)
        self.w(f"Loaded: {name}")

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
        if not self.current.get("uri"):
            return self.ui(messagebox.showerror, "Error", "Import slipnet:// config kwanza")

        uri = self.current["uri"]
        socks_port = int(self.current.get("socks_port") or SOCKS_PORT)
        resolver_host = self.current.get("resolver_host") or "8.8.8.8"
        override = self.dns_override.get().strip()
        if override:
            resolver_host = override.split(":")[0]

        self.ui(self.w, "Inatafuta slipnet + tun2socks...")
        sn = ensure_slipnet(lambda m: self.ui(self.w, m))
        t2s = ensure_tun2socks(lambda m: self.ui(self.w, m))
        if not sn or not t2s:
            return self.ui(
                messagebox.showerror,
                "Error",
                "slipnet au tun2socks haipatikani. Angalia internet / jaribu tena.",
            )

        try:
            self.res_ip = socket.gethostbyname(resolver_host)
        except Exception:
            self.res_ip = "8.8.8.8"
        if not IP_RE.match(self.res_ip):
            self.res_ip = "8.8.8.8"

        self.up = True
        self.ui(self.btn.config, {"text": "DISCONNECT"})

        # 1) slipnet CLI → local SOCKS
        self.ui(self.w, f"1/3 SlipNet CLI → SOCKS :{socks_port}...")
        cmd = [sn, "--port", str(socks_port)]
        if override:
            cmd += ["--dns", override]
        cmd.append(uri)
        self.spawn(cmd, "slipnet")

        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", socks_port), timeout=1).close()
                break
            except OSError:
                time.sleep(1)
        else:
            self.ui(self.w, "SlipNet SOCKS haikufunguka. Angalia logs.")
            return self.stop()

        # 2) DNS proxy + tun2socks
        self.ui(self.w, "2/3 DNS proxy + tun2socks...")
        self.dns = DNSProxy(socks_port, self.current.get("dns_up", "8.8.8.8") or "8.8.8.8")
        self.dns.start()
        self.spawn(
            [
                t2s,
                "-device",
                f"tun://{TUN}",
                "-proxy",
                f"socks5://127.0.0.1:{socks_port}",
            ],
            "tun2socks",
        )

        # 3) routes
        self.ui(self.w, "3/3 Routes (pkexec)...")
        r = pk(UP % {"tun": TUN, "res": self.res_ip})
        if r.returncode != 0:
            self.ui(self.w, "Routes fail: " + (r.stderr or r.stdout))
            return self.stop()

        self.ui(
            self.status.config,
            {"text": "VPN ON — trafiki yote kupitia SlipNet", "foreground": "green"},
        )
        self.watch()

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

    def on_close(self):
        self.stop()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
