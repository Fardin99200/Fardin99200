"""Publish Reels through the Instagram Graph API (resumable upload, no public video hosting needed)."""
from __future__ import annotations

import time
from pathlib import Path

import requests


class InstagramError(RuntimeError):
    pass


def _check(r: requests.Response) -> dict:
    data = r.json() if r.content else {}
    if r.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        msg = err.get("message", r.text[:300])
        if err.get("code") == 190:
            msg += " -> Access token expired/invalid. README ke 'Instagram setup' se naya token banao."
        raise InstagramError(msg)
    return data


def post_reel(file: Path, caption: str, ig_user_id: str, token: str, graph_version: str = "v23.0") -> str:
    graph = f"https://graph.facebook.com/{graph_version}"
    if not token:
        raise InstagramError("Instagram token missing in .env")

    # 1. create a resumable upload container
    data = _check(requests.post(f"{graph}/{ig_user_id}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption[:2200],
        "share_to_feed": "true", "access_token": token,
    }, timeout=60))
    container_id, upload_uri = data["id"], data["uri"]

    # 2. upload the video bytes
    size = Path(file).stat().st_size
    with open(file, "rb") as f:
        _check(requests.post(upload_uri, data=f, timeout=900, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size),
        }))

    # 3. wait for Instagram to process it
    for _ in range(90):  # up to ~15 minutes
        st = _check(requests.get(f"{graph}/{container_id}",
                                 params={"fields": "status_code,status", "access_token": token}, timeout=30))
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") in {"ERROR", "EXPIRED"}:
            raise InstagramError(f"Instagram processing failed: {st.get('status')}")
        time.sleep(10)
    else:
        raise InstagramError("Instagram processing timed out")

    # 4. publish and fetch the public link
    media = _check(requests.post(f"{graph}/{ig_user_id}/media_publish",
                                 data={"creation_id": container_id, "access_token": token}, timeout=60))
    info = _check(requests.get(f"{graph}/{media['id']}",
                               params={"fields": "permalink", "access_token": token}, timeout=30))
    return info.get("permalink") or f"https://www.instagram.com/reel/{media['id']}/"
