"""Fetch source videos (YouTube, Google Drive, or any yt-dlp supported link) or use local files."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yt_dlp


YT_ID = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})")
DRIVE_ID = re.compile(r"drive\.google\.com/(?:file/d/|open\?(?:.*&)?id=|uc\?(?:.*&)?id=)([A-Za-z0-9_-]{20,})")


def canonical(source: str) -> str:
    """The same video under different links maps to one key (youtu.be, shorts, ?t=, tracking params...)."""
    s = source.strip()
    if Path(s).exists():
        return str(Path(s).resolve())
    m = YT_ID.search(s)
    if m:
        return f"youtube:{m.group(1)}"
    m = DRIVE_ID.search(s)
    if m:
        return f"drive:{m.group(1)}"
    s = re.sub(r"[?&](utm_[a-z]+|si|feature|fbclid|igshid|t)=[^&#]*", "", s).rstrip("?&/")
    return s.lower().replace("://www.", "://")


def source_id(source: str) -> str:
    """Stable short id for a link or file, used for output folder names."""
    path = Path(source)
    if path.exists():
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", path.stem)[:40]
        return f"{stem}_{hashlib.md5(str(path.resolve()).encode()).hexdigest()[:6]}"
    return hashlib.md5(canonical(source).encode()).hexdigest()[:12]


def content_key(video: Path) -> str:
    """Fast fingerprint of a video file: size + first and last 2 MB."""
    size = video.stat().st_size
    h = hashlib.sha1(str(size).encode())
    with open(video, "rb") as f:
        h.update(f.read(2 * 1024 * 1024))
        if size > 4 * 1024 * 1024:
            f.seek(-2 * 1024 * 1024, 2)
            h.update(f.read())
    return h.hexdigest()[:16]


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

    if "dropbox.com" in source:
        source = source.replace("dl=0", "dl=1") if "dl=0" in source else source + ("&" if "?" in source else "?") + "dl=1"
    if "drive.google.com" in source:
        return _fetch_drive(source, out)

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


def _fetch_drive(url: str, out: Path) -> tuple[Path, str]:
    """Google Drive file or folder link (yt-dlp is unreliable for Drive)."""
    import gdown

    if "/folders/" in url:
        files = gdown.download_folder(url, output=str(out), quiet=True) or []
        videos = [Path(f) for f in files if Path(f).suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}]
        if not videos:
            raise RuntimeError("Drive folder mein koi video nahi mili")
        # Campaign folders usually hold one main long video; use the largest file.
        video = max(videos, key=lambda p: p.stat().st_size)
    else:
        file = gdown.download(url, output=str(out) + "/", quiet=True, fuzzy=True)
        if not file:
            raise RuntimeError("Drive file download failed (link 'Anyone with the link' pe set hai?)")
        video = Path(file)
    final = out / f"video{video.suffix.lower()}"
    if video != final:
        video.rename(final)
    (out / "title.txt").write_text(video.stem, encoding="utf-8")
    return final.resolve(), video.stem
