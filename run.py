"""Full clipping automation: link -> download -> transcript -> AI picks moments -> 9:16 captioned clips -> YouTube Shorts.

Examples:
    python run.py --campaign campaign.yaml
    python run.py "https://www.youtube.com/watch?v=XXXX" --clips 3
    python run.py my_video.mp4 --no-upload
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from clipper import download, render, selector, transcribe
from clipper.config import Campaign


def slug(text: str, n: int = 40) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:n] or "clip"


def log_submission(out_dir: Path, row: dict) -> None:
    path = out_dir / "submissions.csv"
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        if new:
            writer.writeheader()
        writer.writerow(row)


def process_source(source: str, c: Campaign, out_root: Path) -> None:
    print(f"\n=== {source}")
    sid = download.source_id(source)
    out_dir = out_root / sid
    done_marker = out_dir / "done.json"
    if done_marker.exists():
        print("  Already processed, skipping (delete the folder to redo).")
        return

    print("[1/4] Downloading...")
    video, title = download.fetch(source, c.download_dir)
    _, _, duration = render.probe(video)
    print(f"  {title or video.name} ({duration/60:.1f} min)")

    print("[2/4] Transcribing...")
    segments = transcribe.transcribe(video, out_dir / "transcript.json", c.whisper_model, c.whisper_language)
    if not segments:
        print("  No speech found, skipping.")
        return

    print("[3/4] Claude is picking the best moments...")
    plan_file = out_dir / "plan.json"
    if plan_file.exists():
        ideas = [selector.ClipIdea(**d) for d in json.loads(plan_file.read_text(encoding="utf-8"))]
    else:
        ideas = selector.pick_clips(segments, title, c)
        plan_file.write_text(json.dumps([i.model_dump() for i in ideas], ensure_ascii=False, indent=2), encoding="utf-8")

    windows = []
    for idea in ideas:
        snapped = selector.snap_to_speech(idea, segments, c, duration)
        if snapped:
            windows.append((*snapped, idea))
    windows = selector.remove_overlaps(windows)[: c.clips_per_video]
    print(f"  {len(windows)} clips selected")

    print("[4/4] Rendering" + (" + uploading" if c.upload else "") + "...")
    for n, (start, end, idea) in enumerate(windows, 1):
        out_file = out_dir / f"{n:02d}_{slug(idea.title)}.mp4"
        print(f"  #{n} [{start:.1f}-{end:.1f}s, score {idea.virality_score}] {idea.title}")
        if not out_file.exists():
            render.render_clip(video, start, end, segments, out_file, c)

        hashtags = list(dict.fromkeys(idea.hashtags + c.required_hashtags))
        description = "\n\n".join(x for x in [idea.description, " ".join(hashtags), c.description_suffix] if x)
        meta = {**idea.model_dump(), "start": start, "end": end, "file": out_file.name,
                "final_description": description, "youtube_url": ""}

        meta_file = out_file.with_suffix(".json")
        if meta_file.exists():
            meta["youtube_url"] = json.loads(meta_file.read_text(encoding="utf-8")).get("youtube_url", "")

        if c.upload and not meta["youtube_url"]:
            from clipper import uploader
            try:
                meta["youtube_url"] = uploader.upload_short(out_file, idea.title, description, hashtags, c.privacy)
                print(f"    -> {meta['youtube_url']}")
            except Exception as e:  # keep going; the clip is still saved locally
                print(f"    Upload failed: {e}")

        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        log_submission(out_root, {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "campaign": c.campaign_name,
            "source": source,
            "clip_file": str(out_file),
            "title": idea.title,
            "youtube_url": meta["youtube_url"],
        })

    done_marker.write_text(json.dumps({"finished": datetime.now().isoformat()}), encoding="utf-8")
    print(f"  Clips saved in: {out_dir}")


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="Vyro clipping automation")
    p.add_argument("sources", nargs="*", help="Video links or local files (in addition to the campaign file)")
    p.add_argument("--campaign", help="Campaign YAML file (see campaign.example.yaml)")
    p.add_argument("--clips", type=int, help="Clips per video")
    p.add_argument("--min", type=int, dest="min_seconds", help="Minimum clip length (seconds)")
    p.add_argument("--max", type=int, dest="max_seconds", help="Maximum clip length (seconds)")
    p.add_argument("--crop", choices=["face", "center", "blur"], help="How to make the video vertical")
    p.add_argument("--no-captions", action="store_true")
    p.add_argument("--upload", action="store_true", help="Upload to YouTube Shorts")
    p.add_argument("--no-upload", action="store_true")
    p.add_argument("--privacy", choices=["private", "unlisted", "public"])
    p.add_argument("--whisper", help="Whisper model: tiny, base, small, medium, large-v3")
    args = p.parse_args()

    c = Campaign.load(args.campaign)
    for attr, val in [("clips_per_video", args.clips), ("min_seconds", args.min_seconds),
                      ("max_seconds", args.max_seconds), ("crop_mode", args.crop),
                      ("privacy", args.privacy), ("whisper_model", args.whisper)]:
        if val is not None:
            setattr(c, attr, val)
    if args.no_captions:
        c.captions = False
    if args.upload:
        c.upload = True
    if args.no_upload:
        c.upload = False

    sources = c.sources + args.sources
    if not sources:
        p.error("Koi video link/file nahi diya. Link do ya --campaign file use karo.")

    out_root = Path(c.output_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    failed = 0
    for src in sources:
        try:
            process_source(src, c, out_root)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            failed += 1
            print(f"  ERROR on {src}: {e}")
    print(f"\nDone. {len(sources) - failed}/{len(sources)} videos OK. Links for Vyro: {out_root / 'submissions.csv'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
