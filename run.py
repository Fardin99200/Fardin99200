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
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from clipper import download, pipeline
from clipper.config import Campaign


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
    out_dir = out_root / download.source_id(source)
    done_marker = out_dir / "done.json"
    if done_marker.exists():
        print("  Already processed, skipping (delete the folder to redo).")
        return

    for meta in pipeline.make_clips(source, c, out_root):
        meta_file = Path(meta["path"]).with_suffix(".json")
        if c.upload:
            from clipper import uploader
            try:
                meta["youtube_url"] = uploader.upload_short(
                    Path(meta["path"]), meta["title"], meta["final_description"], meta["hashtags"], c.privacy)
                print(f"    -> {meta['youtube_url']}")
            except Exception as e:  # keep going; the clip is still saved locally
                print(f"    Upload failed: {e}")
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        log_submission(out_root, {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "campaign": c.campaign_name,
            "source": source,
            "clip_file": meta["path"],
            "title": meta["title"],
            "youtube_url": meta.get("youtube_url", ""),
        })

    out_dir.mkdir(parents=True, exist_ok=True)
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
