"""TikTok posting through the official Content Posting API (Direct Post, file upload).

You need a TikTok developer app (developers.tiktok.com) with Login Kit (Desktop) + Content Posting API,
scopes video.publish (+ video.list for views). Put its keys in .env as TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET
and register the redirect URI that Rare Cash shows in Settings.

Until TikTok audits your app, posts can only be private (SELF_ONLY) and the TikTok account must be private.
Rare Cash then still uploads, but does not submit those posts to Vyro (nobody can see them).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com"
SCOPES = os.getenv("TIKTOK_SCOPES", "user.info.basic,video.publish,video.list")
SINGLE_CHUNK_MAX = 64 * 1024 * 1024
CHUNK = 10 * 1024 * 1024


class TikTokError(RuntimeError):
    pass


def keys() -> tuple[str, str]:
    return os.getenv("TIKTOK_CLIENT_KEY", "").strip(), os.getenv("TIKTOK_CLIENT_SECRET", "").strip()


def redirect_uri(port: int) -> str:
    return f"http://127.0.0.1:{port}/tiktok/callback"


def _redact(text: str) -> str:
    return re.sub(r"(access_token|refresh_token|client_secret|code)=[^&\s\"']+", r"\1=***", str(text))


def _req(method: str, url: str, token: str | None = None, **kw) -> dict:
    headers = kw.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.request(method, url, headers=headers, timeout=kw.pop("timeout", 60), **kw)
    except requests.RequestException as e:
        raise TikTokError(_redact(f"{type(e).__name__}: {e}")) from None
    try:
        data = r.json()
    except ValueError:
        data = {}
    err = data.get("error") or {}
    if r.status_code >= 400 or (isinstance(err, dict) and err.get("code") not in (None, "ok")):
        msg = err.get("message") if isinstance(err, dict) else None
        raise TikTokError(_redact(msg or data.get("error_description") or r.text[:300]))
    return data


# ------------------------------------------------------------------ login (OAuth + PKCE)

_pending: dict[str, tuple[str, str, float]] = {}  # state -> (page, code_verifier, created)


def auth_url(page: str, port: int) -> str:
    key, _ = keys()
    if not key:
        raise TikTokError("TikTok client key set nahi hai (Settings → TikTok app)")
    verifier = secrets.token_urlsafe(48)[:64]
    # TikTok's desktop flow expects the challenge as the hex SHA-256 of the verifier
    challenge = hashlib.sha256(verifier.encode()).hexdigest()
    state = secrets.token_urlsafe(16)
    _pending[state] = (page, verifier, time.time())
    return AUTH_URL + "?" + urlencode({
        "client_key": key, "scope": SCOPES, "response_type": "code", "redirect_uri": redirect_uri(port),
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    })


def finish_auth(code: str, state: str, port: int, token_file_for) -> str:
    """Exchange the code for tokens and save them. Returns the page name."""
    entry = _pending.pop(state, None)
    if not entry or time.time() - entry[2] > 900:
        raise TikTokError("Login purana ho gaya ya galat hai. Dashboard se 'Connect TikTok' dobara dabao.")
    page, verifier, _ = entry
    key, secret = keys()
    data = _req("POST", f"{API}/v2/oauth/token/", headers={"Content-Type": "application/x-www-form-urlencoded"}, data={
        "client_key": key, "client_secret": secret, "code": code, "grant_type": "authorization_code",
        "redirect_uri": redirect_uri(port), "code_verifier": verifier,
    })
    _save(Path(token_file_for(page)), data)
    return page


def _save(path: Path, data: dict) -> dict:
    now = time.time()
    tok = {
        "access_token": data["access_token"], "refresh_token": data.get("refresh_token", ""),
        "expires_at": now + int(data.get("expires_in", 86400)),
        "refresh_expires_at": now + int(data.get("refresh_expires_in", 365 * 86400)),
        "open_id": data.get("open_id", ""), "scope": data.get("scope", ""),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tok), encoding="utf-8")
    return tok


def access_token(token_file: str | Path) -> str:
    path = Path(token_file)
    if not path.exists():
        raise TikTokError("TikTok connect nahi hai (Pages → Connect TikTok)")
    tok = json.loads(path.read_text(encoding="utf-8"))
    if time.time() < tok["expires_at"] - 300:
        return tok["access_token"]
    if not tok.get("refresh_token") or time.time() > tok.get("refresh_expires_at", 0):
        raise TikTokError("TikTok login expire ho gaya. Pages → Connect TikTok dobara karo.")
    key, secret = keys()
    data = _req("POST", f"{API}/v2/oauth/token/", headers={"Content-Type": "application/x-www-form-urlencoded"}, data={
        "client_key": key, "client_secret": secret, "grant_type": "refresh_token",
        "refresh_token": tok["refresh_token"],
    })
    return _save(path, data)["access_token"]


# ------------------------------------------------------------------ posting

def post_video(file: Path, caption: str, token_file: str | Path, privacy: str = "SELF_ONLY",
               username: str = "") -> tuple[str, str, str]:
    """Upload and publish. Returns (url, post_or_publish_id, privacy_used)."""
    token = access_token(token_file)
    info = _req("POST", f"{API}/v2/post/publish/creator_info/query/", token,
                headers={"Content-Type": "application/json; charset=UTF-8"}).get("data", {})
    options = info.get("privacy_level_options") or ["SELF_ONLY"]
    used = privacy if privacy in options else ("SELF_ONLY" if "SELF_ONLY" in options else options[0])

    size = Path(file).stat().st_size
    if size <= SINGLE_CHUNK_MAX:
        chunk, count = size, 1
    else:
        chunk, count = CHUNK, size // CHUNK  # the last chunk carries the remainder
    init = _req("POST", f"{API}/v2/post/publish/video/init/", token,
                headers={"Content-Type": "application/json; charset=UTF-8"},
                json={"post_info": {"title": caption[:2200], "privacy_level": used, "disable_duet": False,
                                    "disable_comment": False, "disable_stitch": False,
                                    "video_cover_timestamp_ms": 1000},
                      "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk,
                                      "total_chunk_count": count}}).get("data", {})
    publish_id, upload_url = init["publish_id"], init["upload_url"]

    with open(file, "rb") as f:
        for i in range(count):
            start = i * chunk
            end = size - 1 if i == count - 1 else start + chunk - 1
            f.seek(start)
            body = f.read(end - start + 1)
            try:
                r = requests.put(upload_url, data=body, timeout=600, headers={
                    "Content-Type": "video/mp4", "Content-Length": str(len(body)),
                    "Content-Range": f"bytes {start}-{end}/{size}"})
            except requests.RequestException as e:
                raise TikTokError(f"Upload fail: {type(e).__name__}") from None
            if r.status_code not in (200, 201, 206):
                raise TikTokError(f"Upload fail ({r.status_code})")

    for _ in range(120):  # up to ~10 minutes
        st = _req("POST", f"{API}/v2/post/publish/status/fetch/", token,
                  headers={"Content-Type": "application/json; charset=UTF-8"},
                  json={"publish_id": publish_id}).get("data", {})
        status = st.get("status")
        if status == "PUBLISH_COMPLETE":
            ids = st.get("publicaly_available_post_id") or st.get("publicly_available_post_id") or []
            if ids:
                handle = username.lstrip("@")
                url = f"https://www.tiktok.com/@{handle}/video/{ids[0]}" if handle else f"https://www.tiktok.com/video/{ids[0]}"
                return url, str(ids[0]), used
            return f"https://www.tiktok.com/@{username.lstrip('@')}" if username else "tiktok:private", publish_id, used
        if status == "FAILED":
            raise TikTokError(f"TikTok ne post reject kiya: {st.get('fail_reason', 'unknown')}")
        time.sleep(5)
    raise TikTokError("TikTok processing timed out")


def get_stats(video_ids: list[str], token_file: str | Path) -> dict:
    """{video_id: (views, likes)} — needs the video.list scope."""
    token = access_token(token_file)
    out = {}
    for i in range(0, len(video_ids), 20):
        data = _req("POST", f"{API}/v2/video/query/?fields=id,view_count,like_count", token,
                    headers={"Content-Type": "application/json; charset=UTF-8"},
                    json={"filters": {"video_ids": video_ids[i:i + 20]}}).get("data", {})
        for v in data.get("videos", []):
            out[str(v["id"])] = (int(v.get("view_count", 0)), int(v.get("like_count", 0)))
    return out
