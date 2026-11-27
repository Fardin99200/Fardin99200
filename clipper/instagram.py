"""Publish Reels through the Instagram Graph API (resumable upload, no public video hosting needed)."""
from __future__ import annotations

import re
import time
from pathlib import Path

import requests


class InstagramError(RuntimeError):
    pass


def _redact(text: str) -> str:
    return re.sub(r"(access_token=|OAuth\s+)[^&\s)'\"]+", r"\1***", text)


def _http(method: str, url: str, **kw) -> requests.Response:
    """requests call whose errors never contain the access token (they end up in logs)."""
    try:
        return requests.request(method, url, **kw)
    except requests.RequestException as e:
        raise InstagramError(_redact(f"{type(e).__name__}: {e}")) from None


def _check(r: requests.Response) -> dict:
    data = r.json() if r.content else {}
    if r.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        msg = err.get("message", r.text[:300])
        if err.get("code") == 190:
            msg += " -> Access token expired/invalid. README ke 'Instagram setup' se naya token banao."
        raise InstagramError(_redact(msg))
    return data


def post_reel(file: Path, caption: str, ig_user_id: str, token: str, graph_version: str = "v23.0") -> tuple[str, str]:
    """Returns (permalink, media_id)."""
    graph = f"https://graph.facebook.com/{graph_version}"
    if not token:
        raise InstagramError("Instagram token missing in .env")

    # 1. create a resumable upload container
    data = _check(_http("POST", f"{graph}/{ig_user_id}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption[:2200],
        "share_to_feed": "true", "access_token": token,
    }, timeout=60))
    container_id, upload_uri = data["id"], data["uri"]

    # 2. upload the video bytes
    size = Path(file).stat().st_size
    with open(file, "rb") as f:
        _check(_http("POST", upload_uri, data=f, timeout=900, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size),
        }))

    # 3. wait for Instagram to process it
    for _ in range(90):  # up to ~15 minutes
        st = _check(_http("GET", f"{graph}/{container_id}",
                                 params={"fields": "status_code,status", "access_token": token}, timeout=30))
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") in {"ERROR", "EXPIRED"}:
            raise InstagramError(f"Instagram processing failed: {st.get('status')}")
        time.sleep(10)
    else:
        raise InstagramError("Instagram processing timed out")

    # 4. publish and fetch the public link
    media = _check(_http("POST", f"{graph}/{ig_user_id}/media_publish",
                                 data={"creation_id": container_id, "access_token": token}, timeout=60))
    info = _check(_http("GET", f"{graph}/{media['id']}",
                               params={"fields": "permalink", "access_token": token}, timeout=30))
    return info.get("permalink") or f"https://www.instagram.com/reel/{media['id']}/", media["id"]


def get_stats(media_id: str, token: str, graph_version: str = "v23.0") -> tuple[int, int]:
    """(views, likes) for one Reel."""
    graph = f"https://graph.facebook.com/{graph_version}"
    likes = _check(_http("GET", f"{graph}/{media_id}", params={"fields": "like_count", "access_token": token},
                                timeout=30)).get("like_count", 0)
    views = 0
    for metric in ("views", "plays"):  # "plays" on older API versions
        try:
            data = _check(_http("GET", f"{graph}/{media_id}/insights",
                                       params={"metric": metric, "access_token": token}, timeout=30))
            views = int(data["data"][0]["values"][0]["value"])
            break
        except (InstagramError, KeyError, IndexError):
            continue
    return views, int(likes)
