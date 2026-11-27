"""Built-in VPN for Rare Cash, using wireproxy (ISC licence, https://github.com/windtf/wireproxy).

wireproxy is a userspace WireGuard client: it needs no VPN app, no driver and no admin rights.
It connects to a WireGuard server (from any VPN provider's .conf file) and opens a local proxy
on 127.0.0.1. Rare Cash then sends its own traffic (Vyro browser, YouTube/Instagram uploads,
stats, downloads) through that proxy. Other programs on the PC are not affected.

Kill switch: once the VPN is ON, the proxy settings stay in place even if the tunnel dies, so
requests fail instead of silently going out from your real IP. Only "VPN OFF" removes them.
"""
from __future__ import annotations

import io
import os
import platform
import re
import socket
import stat
import subprocess
import tarfile
import threading
import time
from pathlib import Path

import requests

VPN_DIR = Path("vpn")
BIN_DIR = VPN_DIR / "bin"
CONF_DIR = VPN_DIR / "configs"
HTTP_PORT = int(os.getenv("RARECASH_VPN_PORT", "25345"))
PROXY_URL = f"http://127.0.0.1:{HTTP_PORT}"
NO_PROXY = "localhost,127.0.0.1,::1,api.anthropic.com"
RELEASE_URL = "https://github.com/windtf/wireproxy/releases/download/wireproxy/wireproxy_{os}_{arch}.tar.gz"
PROXY_ENV = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
_ENV_KEYS = PROXY_ENV + ("NO_PROXY", "no_proxy", "RARECASH_PROXY")
_ORIGINAL_ENV = {k: os.environ.get(k) for k in _ENV_KEYS}  # restored on VPN OFF


class VPNError(RuntimeError):
    pass


def _platform() -> tuple[str, str]:
    os_name = {"Windows": "windows", "Linux": "linux", "Darwin": "darwin"}.get(platform.system())
    machine = platform.machine().lower()
    arch = {"amd64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64", "i386": "386",
            "i686": "386", "x86": "386"}.get(machine)
    if not os_name or not arch:
        raise VPNError(f"Is computer ({platform.system()} {machine}) ke liye VPN engine nahi hai")
    return os_name, arch


def binary_path() -> Path:
    custom = os.getenv("RARECASH_WIREPROXY")
    if custom:
        return Path(custom)
    return BIN_DIR / ("wireproxy.exe" if platform.system() == "Windows" else "wireproxy")


def binary_installed() -> bool:
    return binary_path().exists()


def ensure_binary() -> Path:
    """Download the wireproxy engine once (about 5 MB) from its official GitHub releases."""
    path = binary_path()
    if path.exists():
        return path
    os_name, arch = _platform()
    url = RELEASE_URL.format(os=os_name, arch=arch)
    # direct download (never through a half-configured proxy)
    with requests.Session() as s:
        s.trust_env = False
        r = s.get(url, timeout=120)
    if r.status_code != 200:
        raise VPNError(f"VPN engine download nahi hua ({r.status_code}). README ka 'VPN engine manually' dekho.")
    want = "wireproxy.exe" if os_name == "windows" else "wireproxy"
    with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
        member = next((m for m in tar.getmembers() if m.isfile() and Path(m.name).name == want), None)
        if member is None:
            raise VPNError("VPN engine archive mein binary nahi mili")
        data = tar.extractfile(member).read()  # read only this one file: no path tricks possible
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    tmp.replace(path)
    return path


# ------------------------------------------------------------------ configs (servers)

def _safe_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(name).stem).strip("_")[:40]
    return name or "server"


def _parse(text: str) -> dict:
    """Pick out display info. The private key is never returned."""
    section, info = "", {"address": "", "endpoint": "", "dns": ""}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith("["):
            section = line.lower()
            continue
        if "=" not in line:
            continue
        k, v = (x.strip() for x in line.split("=", 1))
        k = k.lower()
        if section == "[interface]" and k in ("address", "dns"):
            info[k] = v
        elif section == "[peer]" and k == "endpoint" and not info["endpoint"]:
            info["endpoint"] = v
    return info


def validate_config(text: str) -> None:
    t = text.lower()
    if "[interface]" not in t or "privatekey" not in t:
        raise VPNError("Ye WireGuard config nahi lagti ([Interface] aur PrivateKey chahiye)")
    if "[peer]" not in t or "endpoint" not in t:
        raise VPNError("Config mein [Peer] Endpoint nahi hai")
    if "publickey" not in t:
        raise VPNError("Config mein [Peer] PublicKey nahi hai")


def save_config(name: str, text: str) -> str:
    validate_config(text)
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    safe = _safe_name(name)
    path = CONF_DIR / f"{safe}.conf"
    path.write_text(text.strip() + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return safe


def delete_config(name: str) -> None:
    path = CONF_DIR / f"{_safe_name(name)}.conf"
    if path.exists():
        path.unlink()


def list_configs() -> list[dict]:
    if not CONF_DIR.exists():
        return []
    out = []
    for p in sorted(CONF_DIR.glob("*.conf")):
        info = _parse(p.read_text(encoding="utf-8", errors="replace"))
        out.append({"name": p.stem, "endpoint": info["endpoint"].rsplit(":", 1)[0], "address": info["address"]})
    return out


# ------------------------------------------------------------------ the tunnel

def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def set_proxy_env(on: bool) -> None:
    if on:
        for k in PROXY_ENV:
            os.environ[k] = PROXY_URL
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = NO_PROXY
        os.environ["RARECASH_PROXY"] = PROXY_URL
        return
    for k, v in _ORIGINAL_ENV.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class Tunnel:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.config: str = ""
        self.state = "off"          # off | connecting | on | error
        self.error = ""
        self.since = 0.0
        self.country = ""
        self.ip = ""
        self.lock = threading.RLock()
        self._log = None
        self.last_check = 0.0

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, name: str) -> dict:
        with self.lock:
            self.stop(clear_env=False)
            conf = CONF_DIR / f"{_safe_name(name)}.conf"
            if not conf.exists():
                raise VPNError(f"Server '{name}' nahi mila. Pehle WireGuard config add karo.")
            self.config, self.state, self.error = conf.stem, "connecting", ""
            set_proxy_env(True)  # kill switch first: nothing leaves directly from now on
            try:
                exe = ensure_binary()
                if _port_open(HTTP_PORT):
                    raise VPNError(f"Port {HTTP_PORT} pe pehle se kuch chal raha hai (RARECASH_VPN_PORT badlo)")
                VPN_DIR.mkdir(exist_ok=True)
                runtime = VPN_DIR / "wireproxy.conf"
                runtime.write_text(f"WGConfig = {conf.resolve()}\n\n[http]\nBindAddress = 127.0.0.1:{HTTP_PORT}\n",
                                   encoding="utf-8")
                self._log = open(VPN_DIR / "wireproxy.log", "ab")
                flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                self.proc = subprocess.Popen([str(exe), "-c", str(runtime.resolve())], stdout=self._log,
                                             stderr=subprocess.STDOUT, creationflags=flags)
                for _ in range(40):
                    if _port_open(HTTP_PORT) or not self.running():
                        break
                    time.sleep(0.25)
                if not self.running():
                    raise VPNError("VPN engine band ho gaya. Config sahi hai? (vpn/wireproxy.log dekho)")
                self.check()
                return self.status()
            except Exception as e:
                self.state, self.error = "error", str(e)
                raise

    def check(self) -> dict:
        """Ask ipinfo.io through the tunnel which country we appear to be in."""
        self.last_check = time.time()
        from . import network
        network._cache["at"] = 0  # the old (pre-VPN) location is stale now
        try:
            r = requests.get("https://ipinfo.io/json", timeout=15,
                             proxies={"http": PROXY_URL, "https": PROXY_URL})
            data = r.json()
            self.country, self.ip = (data.get("country") or "").upper(), data.get("ip", "")
            self.state, self.error = "on", ""
            if not self.since:
                self.since = time.time()
        except Exception as e:
            self.state = "error"
            self.error = "VPN server se connect nahi hua (internet ya config check karo)"
            self.country = self.ip = ""
        return self.status()

    def stop(self, clear_env: bool = True) -> None:
        with self.lock:
            if self.proc and self.running():
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            self.proc = None
            if self._log:
                self._log.close()
                self._log = None
            self.since = 0.0
            if clear_env:
                set_proxy_env(False)
                from . import network
                network._cache["at"] = 0
                self.state, self.config, self.error, self.country, self.ip = "off", "", "", "", ""

    def watchdog(self, wanted: bool, name: str) -> None:
        """Called regularly by the engine: keep the tunnel up while VPN is switched ON."""
        if not wanted:
            if self.state != "off":
                self.stop()
            return
        if not name:
            return
        if not self.running() or self.config != _safe_name(name):
            try:
                self.start(name)
            except Exception:
                pass  # state/error already recorded; kill switch stays on
        elif time.time() - self.last_check > 120:
            self.check()  # process alive, but is the server still reachable?

    def status(self) -> dict:
        ip = self.ip
        parts = ip.split(".")
        masked = ".".join(parts[:2] + ["x", "x"]) if len(parts) == 4 else ip
        return {"state": self.state if (self.state == "off" or self.running()) else "error",
                "config": self.config, "error": self.error or ("" if self.state == "off" or self.running()
                                                              else "VPN engine ruk gaya, dobara jod raha hai"),
                "country": self.country, "ip": masked, "since": self.since,
                "engine_installed": binary_installed(), "port": HTTP_PORT}


tunnel = Tunnel()
