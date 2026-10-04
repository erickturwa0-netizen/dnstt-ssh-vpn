#!/usr/bin/env python3
"""DNSTT / Slipstream + SSH full-system VPN GUI (Linux).

- Jaza details au IMPORT dnst:// URL / config
- Protocol: DNSTT au Slipstream
- App inatafuta/kupakua binaries otomatiki
"""
import base64, json, os, platform, re, shutil, socket, struct, subprocess, threading, time, tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from urllib.parse import urlparse, parse_qs, unquote
from urllib.request import urlretrieve

CFG_DIR = os.path.expanduser("~/.config/dnstt-ssh-vpn")
BIN_DIR = os.path.join(CFG_DIR, "bin")
CFG = os.path.join(CFG_DIR, "last.json")
PROFILES = os.path.join(CFG_DIR, "profiles.json")

FIELDS = [
    ("protocol", "Protocol (dnstt / slipstream)", "dnstt"),
    ("mode", "Mode DNSTT (udp/doh/dot)", "udp"),
    ("resolver", "Dns resolve (8.8.8.8:53 / DoH)", "8.8.8.8:53"),
    ("domain", "NS / Tunnel domain", ""),
    ("pubkey", "PUBLIC KEY (DNSTT only)", ""),
    ("ssh_host", "SSH HOST", "127.0.0.1"),
    ("ssh_port", "SSH PORT (local tunnel)", "7000"),
    ("ssh_user", "USERNAME", ""),
    ("ssh_pass", "PASSWORD", ""),
    ("dns_up", "DNS upstream (kupitia tunnel)", "8.8.8.8"),
]
SOCKS_PORT = "1080"
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


def download_binaries(log_fn, need_slipstream=False):
    os.makedirs(BIN_DIR, exist_ok=True)
    arch = goarch()
    results = {}

    # tun2socks (always)
    t2s = find_binary("tun2socks")
    if not t2s:
        log_fn("Inapakua tun2socks...")
        zip_name = f"tun2socks-linux-{arch}.zip"
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
                    t2s = dest
                    break
            log_fn(f"tun2socks: {t2s}")
        except Exception as e:
            log_fn(f"tun2socks download fail: {e}")
    results["tun2socks"] = t2s

    if need_slipstream:
        ss = find_binary("slipstream-client")
        if not ss:
            log_fn("Inapakua slipstream-client...")
            # Prefer AliRezaBeigy prebuilt (linux-amd64 / arm64)
            url = f"https://github.com/AliRezaBeigy/slipstream-rust-deploy/releases/latest/download/slipstream-client-linux-{arch}"
            dest = os.path.join(BIN_DIR, "slipstream-client")
            try:
                urlretrieve(url, dest)
                os.chmod(dest, 0o755)
                ss = dest
                log_fn(f"slipstream-client: {dest}")
            except Exception as e:
                log_fn(f"slipstream download fail: {e}")
        results["slipstream"] = ss
    else:
        dnstt = find_binary("dnstt-client")
        if not dnstt:
            log_fn("Inapakua dnstt-client...")
            url = f"https://github.com/net2share/dnstt/releases/latest/download/dnstt-client-linux-{arch}"
            dest = os.path.join(BIN_DIR, "dnstt-client")
            try:
                urlretrieve(url, dest)
                os.chmod(dest, 0o755)
                dnstt = dest
                log_fn(f"dnstt-client: {dest}")
            except Exception as e:
                log_fn(f"dnstt download fail: {e}")
        results["dnstt"] = dnstt

    return results


def parse_dnst_url(text):
    """Parse dnst:// URL (human or base64-JSON) into field dict."""
    text = text.strip()
    if not text:
        raise ValueError("Config tupu")

    out = {}

    # base64-json form: dnst://eyJ...
    if text.startswith("dnst://") and "/" not in text[7:].split("?")[0].split("#")[0]:
        b64 = text[7:].split("#")[0]
        pad = "=" * ((4 - len(b64) % 4) % 4)
        try:
            raw = base64.urlsafe_b64decode(b64 + pad)
            data = json.loads(raw)
        except Exception as e:
            raise ValueError(f"Base64 JSON batili: {e}") from e
        tag = data.get("tag") or ""
        tr = data.get("transport") or {}
        be = data.get("backend") or {}
        out["protocol"] = (tr.get("type") or "dnstt").lower()
        out["domain"] = tr.get("domain") or ""
        out["pubkey"] = tr.get("pubkey") or ""
        if be.get("type") == "ssh":
            out["ssh_user"] = be.get("user") or ""
            out["ssh_pass"] = be.get("password") or ""
        if tag:
            out["_profile_name"] = tag
        return out

    # human form: dnst://domain/transport/backend?params#tag
    if text.startswith("dnst://"):
        u = urlparse(text)
        # hostname = domain, path = /transport/backend
        domain = u.hostname or ""
        parts = [p for p in (u.path or "").strip("/").split("/") if p]
        transport = (parts[0] if parts else "dnstt").lower()
        backend = (parts[1] if len(parts) > 1 else "ssh").lower()
        qs = parse_qs(u.query)
        def q(k, default=""):
            return unquote(qs[k][0]) if k in qs and qs[k] else default

        out["protocol"] = "slipstream" if "slip" in transport else transport
        out["domain"] = domain
        out["pubkey"] = q("pubkey")
        if backend == "ssh":
            out["ssh_user"] = q("user")
            out["ssh_pass"] = q("password")
        if u.fragment:
            out["_profile_name"] = unquote(u.fragment)
        return out

    # try plain JSON
    if text.startswith("{"):
        data = json.loads(text)
        out["protocol"] = (data.get("protocol") or data.get("transport") or "dnstt").lower()
        if isinstance(out["protocol"], dict):
            out["protocol"] = out["protocol"].get("type", "dnstt")
        out["domain"] = data.get("domain") or data.get("ns") or ""
        out["pubkey"] = data.get("pubkey") or data.get("public_key") or ""
        out["ssh_user"] = data.get("ssh_user") or data.get("user") or data.get("username") or ""
        out["ssh_pass"] = data.get("ssh_pass") or data.get("password") or ""
        out["resolver"] = data.get("resolver") or data.get("dns_resolve") or ""
        out["ssh_port"] = str(data.get("ssh_port") or data.get("port") or "")
        return out

    raise ValueError("Format haijulikani. Tumia dnst:// URL au JSON.")


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
        self.title("DNSTT / Slipstream + SSH VPN")
        self.geometry("620x820")
        self.procs, self.dns, self.res_ip, self.up = [], None, None, False

        cfg = load_json(CFG, {})
        self.profiles = load_json(PROFILES, {})
        self.vars = {}

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        # ---- Import ----
        imp = ttk.LabelFrame(outer, text="Import config (dnst:// au JSON)", padding=6)
        imp.pack(fill="x", pady=(0, 6))
        self.import_box = scrolledtext.ScrolledText(imp, height=3, wrap="word")
        self.import_box.pack(fill="x", pady=2)
        ttk.Button(imp, text="IMPORT & FILL FIELDS", command=self.do_import).pack(fill="x")

        # ---- Fields ----
        f = ttk.LabelFrame(outer, text="Connection settings", padding=8)
        f.pack(fill="x", pady=(0, 6))
        for i, (k, label, d) in enumerate(FIELDS):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w", pady=2, padx=(0, 8))
            v = tk.StringVar(value=cfg.get(k, d))
            self.vars[k] = v
            show = "*" if k == "ssh_pass" else ""
            ttk.Entry(f, textvariable=v, width=40, show=show).grid(row=i, column=1, sticky="ew", pady=2)
        f.columnconfigure(1, weight=1)

        self.btn = ttk.Button(outer, text="CONNECT VPN", command=self.toggle)
        self.btn.pack(fill="x", pady=4)
        self.status = ttk.Label(outer, text="Disconnected", foreground="red")
        self.status.pack()
        self.log = tk.Text(outer, height=9, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, pady=4)

        # ---- Profiles ----
        pf = ttk.LabelFrame(outer, text="Profiles", padding=6)
        pf.pack(fill="x")
        row0 = ttk.Frame(pf)
        row0.pack(fill="x", pady=2)
        ttk.Label(row0, text="PROFILE NAME").pack(side="left")
        self.profile_name = tk.StringVar()
        ttk.Entry(row0, textvariable=self.profile_name, width=26).pack(
            side="left", padx=6, fill="x", expand=True
        )
        row1 = ttk.Frame(pf)
        row1.pack(fill="x", pady=2)
        self.profile_combo = ttk.Combobox(row1, state="readonly", width=22)
        self.profile_combo.pack(side="left", padx=(0, 6))
        ttk.Button(row1, text="Load", command=self.load_selected_profile).pack(side="left", padx=2)
        ttk.Button(row1, text="Delete", command=self.delete_profile).pack(side="left", padx=2)
        ttk.Button(pf, text="SAVE PROFILE", command=self.save_profile).pack(fill="x", pady=4)

        self.refresh_profile_list()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def do_import(self):
        raw = self.import_box.get("1.0", "end").strip()
        try:
            data = parse_dnst_url(raw)
        except Exception as e:
            return messagebox.showerror("Import", str(e))
        for k, v in data.items():
            if k.startswith("_"):
                continue
            if k in self.vars and v is not None and str(v) != "":
                self.vars[k].set(str(v))
        if data.get("_profile_name"):
            self.profile_name.set(data["_profile_name"])
        self.w(f"Imported: protocol={data.get('protocol')} domain={data.get('domain')}")
        messagebox.showinfo("Import", "Config imewekwa kwenye fields. Angalia na CONNECT / SAVE.")

    def refresh_profile_list(self):
        names = sorted(self.profiles.keys())
        self.profile_combo["values"] = names
        if names and not self.profile_combo.get():
            self.profile_combo.set(names[0])

    def current_values(self):
        return {k: v.get().strip() for k, v in self.vars.items()}

    def apply_values(self, data):
        for k, v in self.vars.items():
            if k in data:
                v.set(str(data[k]))

    def save_profile(self):
        name = self.profile_name.get().strip()
        if not name:
            return messagebox.showerror("Error", "Andika PROFILE NAME kwanza")
        self.profiles[name] = self.current_values()
        save_json(PROFILES, self.profiles)
        save_json(CFG, self.profiles[name])
        self.refresh_profile_list()
        self.profile_combo.set(name)
        messagebox.showinfo("Saved", f"Profile '{name}' imehifadhiwa.")

    def load_selected_profile(self):
        name = self.profile_combo.get()
        if not name or name not in self.profiles:
            return messagebox.showerror("Error", "Chagua profile kwanza")
        self.apply_values(self.profiles[name])
        self.profile_name.set(name)
        save_json(CFG, self.profiles[name])
        self.w(f"Loaded profile: {name}")

    def delete_profile(self):
        name = self.profile_combo.get()
        if not name or name not in self.profiles:
            return
        if not messagebox.askyesno("Delete", f"Futa profile '{name}'?"):
            return
        del self.profiles[name]
        save_json(PROFILES, self.profiles)
        self.profile_name.set("")
        self.refresh_profile_list()
        self.profile_combo.set("" if not self.profiles else sorted(self.profiles.keys())[0])

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
        g = self.current_values()
        proto = (g.get("protocol") or "dnstt").lower()
        if "slip" in proto:
            proto = "slipstream"

        if not g["domain"]:
            return self.ui(messagebox.showerror, "Error", "NS / Tunnel domain inahitajika")
        if not g["ssh_user"]:
            return self.ui(messagebox.showerror, "Error", "USERNAME inahitajika")
        if proto == "dnstt" and not g["pubkey"]:
            return self.ui(messagebox.showerror, "Error", "PUBLIC KEY inahitajika kwa DNSTT")

        save_json(CFG, g)

        need_ss = proto == "slipstream"
        self.ui(self.w, f"Protocol: {proto} — inatafuta binaries...")
        bins = download_binaries(lambda m: self.ui(self.w, m), need_slipstream=need_ss)
        t2s = bins.get("tun2socks") or find_binary("tun2socks")
        if not t2s:
            return self.ui(messagebox.showerror, "Error", "tun2socks haipatikani")

        host = (
            urlparse(g["resolver"]).hostname
            if "://" in g["resolver"]
            else g["resolver"].rsplit(":", 1)[0]
        )
        try:
            self.res_ip = socket.gethostbyname(host)
        except Exception:
            return self.ui(messagebox.showerror, "Error", "Dns resolve haijulikani")
        if not IP_RE.match(self.res_ip):
            return self.ui(messagebox.showerror, "Error", "Dns resolve si IP sahihi")

        local_port = g["ssh_port"] or "7000"
        ssh_target = g["ssh_host"] or "127.0.0.1"

        self.up = True
        self.ui(self.btn.config, {"text": "DISCONNECT"})

        if proto == "slipstream":
            ss = bins.get("slipstream") or find_binary("slipstream-client")
            if not ss:
                self.up = False
                return self.ui(messagebox.showerror, "Error", "slipstream-client haipatikani")
            # resolver for slipstream: host:port form preferred
            resolver = g["resolver"]
            if "://" in resolver:
                # DoH URL not used by classic slipstream-client; use 8.8.8.8:53 fallback
                resolver = "8.8.8.8:53"
                self.ui(self.w, "Slipstream: DoH haikubaliwi, natumia 8.8.8.8:53")
            self.ui(self.w, "1/4 Slipstream...")
            # Common CLI: --tcp-listen-port --resolver/--resolver-address --domain
            cmd = [
                ss,
                "--tcp-listen-port", local_port,
                "--resolver", resolver,
                "--domain", g["domain"],
            ]
            self.spawn(cmd, "slipstream")
            time.sleep(3)
        else:
            dnstt = bins.get("dnstt") or find_binary("dnstt-client")
            if not dnstt:
                self.up = False
                return self.ui(messagebox.showerror, "Error", "dnstt-client haipatikani")
            flag = {"udp": "-udp", "doh": "-doh", "dot": "-dot"}.get(g["mode"].lower(), "-udp")
            key = (
                ["-pubkey-file", g["pubkey"]]
                if os.path.isfile(g["pubkey"])
                else ["-pubkey", g["pubkey"]]
            )
            self.ui(self.w, "1/4 DNSTT...")
            self.spawn(
                [dnstt, flag, g["resolver"], *key, g["domain"], f"127.0.0.1:{local_port}"],
                "dnstt",
            )
            time.sleep(2)

        self.ui(self.w, "2/4 SSH...")
        ssh = [
            "ssh", "-N", "-D", f"127.0.0.1:{SOCKS_PORT}",
            "-p", local_port,
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ServerAliveInterval=15",
            "-o", "ExitOnForwardFailure=yes",
            f"{g['ssh_user']}@{ssh_target}",
        ]
        env = os.environ.copy()
        if g["ssh_pass"]:
            env["SSHPASS"] = g["ssh_pass"]
            ssh = ["sshpass", "-e"] + ssh
        self.spawn(ssh, "ssh", env)

        sp = int(SOCKS_PORT)
        for _ in range(45):
            try:
                socket.create_connection(("127.0.0.1", sp), timeout=1).close()
                break
            except OSError:
                time.sleep(1)
        else:
            self.ui(self.w, "SSH haikuunganika. Angalia logs.")
            return self.stop()

        self.ui(self.w, "3/4 DNS proxy + tun2socks...")
        self.dns = DNSProxy(sp, g["dns_up"] or "8.8.8.8")
        self.dns.start()
        self.spawn(
            [t2s, "-device", f"tun://{TUN}", "-proxy", f"socks5://127.0.0.1:{sp}"],
            "tun2socks",
        )
        self.ui(self.w, "4/4 Routes (pkexec)...")
        r = pk(UP % {"tun": TUN, "res": self.res_ip})
        if r.returncode != 0:
            self.ui(self.w, "Routes zimeshindwa: " + (r.stderr or r.stdout))
            return self.stop()
        self.ui(self.status.config, {"text": "VPN ON", "foreground": "green"})
        self.watch()

    def spawn(self, cmd, name, env=None):
        p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.procs.append(p)

        def rd():
            for line in p.stdout:
                self.ui(self.w, f"[{name}] {line.rstrip()}")

        threading.Thread(target=rd, daemon=True).start()

    def watch(self):
        while self.up:
            time.sleep(2)
            if any(p.poll() is not None for p in self.procs):
                self.ui(self.w, "Process imesimama, nazima VPN.")
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
