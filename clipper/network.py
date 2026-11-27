"""VPN guard: check which country the PC's internet appears to come from.

Rare Cash does not provide a VPN. You run your own VPN app system-wide; this only checks it is
connected, so the bot doesn't open Vyro or post while the VPN has dropped.
"""
from __future__ import annotations

import time

import requests

_cache: dict = {"at": 0.0, "info": None}

COUNTRY_NAMES = {
    "US": "United States", "GB": "United Kingdom", "CA": "Canada", "AU": "Australia", "NZ": "New Zealand",
    "DE": "Germany", "FR": "France", "NL": "Netherlands", "IE": "Ireland", "SE": "Sweden", "NO": "Norway",
    "DK": "Denmark", "CH": "Switzerland", "IN": "India", "AE": "UAE", "SG": "Singapore", "PK": "Pakistan",
    "BD": "Bangladesh",
}


def public_location(max_age: float = 60) -> dict:
    """{'ip', 'country', 'country_name', 'ok'}; cached for `max_age` seconds."""
    if _cache["info"] and time.time() - _cache["at"] < max_age:
        return _cache["info"]
    info = {"ip": "", "country": "", "country_name": "", "ok": False}
    for url, key in (("https://ipinfo.io/json", "country"), ("https://api.country.is/", "country")):
        try:
            data = requests.get(url, timeout=8).json()
            code = (data.get(key) or "").upper()
            if code:
                info = {"ip": data.get("ip", ""), "country": code,
                        "country_name": COUNTRY_NAMES.get(code, code), "ok": True}
                break
        except Exception:
            continue
    _cache.update(at=time.time(), info=info)
    return info


def masked_ip(ip: str) -> str:
    parts = ip.split(".")
    return ".".join(parts[:2] + ["x", "x"]) if len(parts) == 4 else (ip[:8] + "…" if ip else "")


def vpn_status(allowed: list[str], required: bool, max_age: float = 60) -> dict:
    loc = public_location(max_age)
    allowed_up = [c.upper() for c in allowed]
    in_allowed = loc["ok"] and (not allowed_up or loc["country"] in allowed_up)
    return {
        **loc,
        "ip": masked_ip(loc["ip"]),
        "required": required,
        "allowed": allowed_up,
        # when the guard is off, never block the bot
        "pass": (not required) or in_allowed,
    }
