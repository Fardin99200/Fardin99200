"""Fetch source videos (YouTube, Google Drive, or any yt-dlp supported link) or use local files."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yt_dlp


def source_id(source: str) -> str:
    """Stable short id for a link or file, used for output folder names."""
    path = Path(source)
    if path.exists():
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", path.stem)[:40]
        return f"{stem}_{hashlib.md5(str(path.resolve()).encode()).hexdigest()[:6]}"
    return hashlib.md5(source.encode()).hexdigest()[:12]


def fetch(source: str, download_dir: str | Path) -> tuple[Path, str]:
    """Return (local video path, title). Downloads if `source` is a URL."""
    path = Path(source)
    if path.exists():
        return path.resolve(), path.stem

    out = Path(download_dir) / source_id(source)
    out.mkdir(parents=True, exist_ok=True)
    existing = sorted(out.glob("video.*"))
    existing = [p for p in existing if p.suffix in {".mp4", ".mkv", ".webm", ".mov"}]
    if existing:
        title = (out / "title.txt").read_text(encoding="utf-8") if (out / "title.txt").exists() else ""
        return existing[0].resolve(), title

    opts = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(out / "video.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(source, download=True)
        file = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
        if not file.exists():
            file = next(p for p in out.glob("video.*") if p.suffix != ".part")
    title = info.get("title") or ""
    (out / "title.txt").write_text(title, encoding="utf-8")
    return file.resolve(), title
