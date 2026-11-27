"""One source video -> rendered, captioned 9:16 clips with metadata (no posting)."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from . import download, render, selector
from . import transcribe as stt
from .config import Campaign


def slug(text: str, n: int = 40) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:n] or "clip"


def make_clips(source: str, c: Campaign, out_root: Path) -> list[dict]:
    """Returns a list of clip metadata dicts (each has 'path', 'title', 'description', 'hashtags', ...).
    Results are cached on disk, so calling again for the same source is cheap."""
    sid = download.source_id(source)
    out_dir = out_root / sid
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[1/4] Downloading...")
    video, title = download.fetch(source, c.download_dir)
    _, _, duration = render.probe(video)
    print(f"  {title or video.name} ({duration/60:.1f} min)")

    print("[2/4] Transcribing...")
    segments = stt.transcribe(video, out_dir / "transcript.json", c.whisper_model, c.whisper_language)
    if not segments:
        print("  No speech found, skipping.")
        return []

    print("[3/4] Claude is picking the best moments...")
    # Source already short (common with campaign material): keep the whole thing as one clip.
    pick_cfg = c
    if duration <= c.max_seconds + 5:
        pick_cfg = copy.copy(c)
        pick_cfg.clips_per_video = 1
        pick_cfg.min_seconds = max(3, int(duration * 0.7))
        pick_cfg.max_seconds = int(duration) + 1

    plan_file = out_dir / "plan.json"
    if plan_file.exists():
        ideas = [selector.ClipIdea(**d) for d in json.loads(plan_file.read_text(encoding="utf-8"))]
    else:
        ideas = selector.pick_clips(segments, title, pick_cfg)
        plan_file.write_text(json.dumps([i.model_dump() for i in ideas], ensure_ascii=False, indent=2), encoding="utf-8")

    windows = []
    for idea in ideas:
        snapped = selector.snap_to_speech(idea, segments, pick_cfg, duration)
        if snapped:
            windows.append((*snapped, idea))
    windows = selector.remove_overlaps(windows)[: pick_cfg.clips_per_video]
    print(f"  {len(windows)} clips selected")

    print("[4/4] Rendering...")
    results = []
    for n, (start, end, idea) in enumerate(windows, 1):
        out_file = out_dir / f"{n:02d}_{slug(idea.title)}.mp4"
        print(f"  #{n} [{start:.1f}-{end:.1f}s, score {idea.virality_score}] {idea.title}")
        if not out_file.exists():
            render.render_clip(video, start, end, segments, out_file, c, hook=idea.title)

        hashtags = list(dict.fromkeys(idea.hashtags + c.required_hashtags))
        description = "\n\n".join(x for x in [idea.description, " ".join(hashtags), c.description_suffix] if x)
        meta = {**idea.model_dump(), "start": start, "end": end, "path": str(out_file.resolve()),
                "source": source, "hashtags": hashtags, "final_description": description}
        out_file.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(meta)
    return results
