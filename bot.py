"""24x7 Vyro clipping bot.

Loop: scan Vyro campaigns -> route to niche pages -> join + read material -> make clips ->
post on YouTube Shorts / Instagram Reels (rate-limited per page) -> submit post links on Vyro.

    python bot.py --login          # one time: log in to Vyro in the bot's browser
    python bot.py --setup-youtube  # one time: connect each page's YouTube channel
    python bot.py                  # run forever
    python bot.py --once           # one cycle (for testing)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from clipper import instagram, pipeline, uploader, vyro
from clipper.botconfig import BotConfig, Page
from clipper.browser_agent import Browser
from clipper.config import Campaign
from clipper.state import State

log = logging.getLogger("bot")
OUT = Path("output")


def setup_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler("logs/bot.log", encoding="utf-8")):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def browser(cfg: BotConfig) -> Browser:
    return Browser(cfg.vyro.profile_dir, cfg.vyro.allowed_domains, cfg.vyro.headless)


def page_platforms(page: Page) -> list[str]:
    out = []
    if page.youtube and page.youtube.enabled:
        out.append("youtube")
    if page.instagram and page.instagram.enabled:
        out.append("instagram")
    return out


def platform_allowed(platform: str, campaign_platforms: list[str]) -> bool:
    if not campaign_platforms:
        return True  # campaign didn't say; assume all
    names = {"youtube": ("youtube", "shorts", "yt"), "instagram": ("instagram", "reels", "ig")}
    return any(any(n in p.lower() for n in names[platform]) for p in campaign_platforms)


# ---------------------------------------------------------------- 1. scan

def scan(cfg: BotConfig, st: State) -> None:
    log.info("Scanning Vyro campaigns...")
    with browser(cfg) as b:
        found = vyro.scan_campaigns(b, cfg)
        log.info(f"  {len(found)} campaigns on Vyro")
        new = [c for c in found if c.get("url") and not st.campaign_known(c["url"])]
        if not new:
            return
        routes = {r.url: r for r in vyro.route_campaigns(new, cfg)}
        accepted = 0
        for c in new:
            r = routes.get(c["url"])
            page = r.page if r and cfg.page(r.page) else ""
            cpm_ok = r is None or r.cpm_usd is None or r.cpm_usd >= cfg.vyro.min_cpm_usd
            usable = page and cpm_ok and any(platform_allowed(p, c.get("platforms") or [])
                                             for p in page_platforms(cfg.page(page)))
            if not usable or accepted >= cfg.vyro.max_new_campaigns_per_scan:
                # leave over-limit campaigns unknown so a later scan can pick them up
                if not usable:
                    st.add_campaign(c["url"], c.get("title", ""), c, "", "skipped")
                    log.info(f"  skip: {c.get('title')} ({r.reason if r else 'no route'})")
                continue
            try:
                details = vyro.campaign_details(b, cfg, c["url"])
            except vyro.LoginRequired:
                raise
            except Exception as e:
                log.warning(f"  could not open {c.get('title')}: {e}")
                continue
            if not details.get("active", True) or not details.get("material_links"):
                st.add_campaign(c["url"], c.get("title", ""), {**c, **details}, "", "skipped")
                log.info(f"  skip (inactive/no material): {c.get('title')}")
                continue
            st.add_campaign(c["url"], c.get("title", ""), {**c, **details}, page, "ready")
            accepted += 1
            log.info(f"  + {c.get('title')} -> page '{page}' ({len(details['material_links'])} links)")


# ---------------------------------------------------------------- 2. clips

def campaign_settings(cfg: BotConfig, page: Page, data: dict) -> Campaign:
    c = Campaign(**cfg.clip_defaults)
    c.campaign_name = data.get("title", "")
    c.rules = data.get("rules", "")
    c.language = page.language
    c.clips_per_video = page.clips_per_video
    if data.get("min_seconds"):
        c.min_seconds = int(data["min_seconds"])
    if data.get("max_seconds"):
        c.max_seconds = min(int(data["max_seconds"]), 90)
    c.description_suffix = data.get("required_caption", "") or ""
    c.upload = False
    return c


def make_clips(cfg: BotConfig, st: State) -> None:
    """Process one ready campaign per cycle so posting keeps flowing."""
    ready = st.campaigns("ready")
    if not ready:
        return
    row = ready[0]
    data, page = json.loads(row["data"]), cfg.page(row["page"])
    if page is None:
        st.update_campaign(row["url"], status="skipped", error="page removed from bot.yaml")
        return
    c = campaign_settings(cfg, page, data)
    log.info(f"Making clips for '{row['title']}' (page {page.name})")
    links = [u for u in data.get("material_links", []) if not st.material_done(u, row["url"])]
    for link in links[: cfg.vyro.max_materials_per_campaign]:
        try:
            source = link
            host = (urlparse(link).hostname or "").lower()
            if any(host == d or host.endswith("." + d) for d in cfg.vyro.allowed_domains):
                # file hosted on Vyro itself: download with the logged-in session
                dest = Path(c.download_dir) / "vyro" / (Path(urlparse(link).path).name or "material.mp4")
                with browser(cfg) as b:
                    source = str(b.download(link, dest))
            clips = pipeline.make_clips(source, c, OUT / page.name)
            for meta in clips:
                st.add_clip(row["url"], page.name, meta)
            st.mark_material(link, row["url"], "done")
            log.info(f"  {len(clips)} clips from {link}")
        except Exception as e:
            st.mark_material(link, row["url"], "failed", str(e)[:500])
            log.warning(f"  material failed {link}: {e}")
    remaining = [u for u in data.get("material_links", []) if not st.material_done(u, row["url"])]
    if not remaining or len(data.get("material_links", [])) - len(remaining) >= cfg.vyro.max_materials_per_campaign:
        st.update_campaign(row["url"], status="done")


# ---------------------------------------------------------------- 3. post

def post_due(cfg: BotConfig, st: State) -> None:
    for page in cfg.pages:
        for platform in page_platforms(page):
            limit = page.youtube.max_per_day if platform == "youtube" else page.instagram.max_per_day
            recent = st.posts_since(page.name, platform, 24)
            if len(recent) >= limit:
                continue
            if recent:
                last = datetime.fromisoformat(recent[0]["posted_at"])
                if (datetime.now(timezone.utc) - last).total_seconds() < page.min_gap_minutes * 60:
                    continue
            clip = pick_clip(st, page.name, platform)
            if clip is None:
                continue
            meta = json.loads(clip["meta"])
            log.info(f"Posting to {page.name}/{platform}: {meta['title']}")
            try:
                url = publish(page, platform, meta)
                st.record_post(clip["id"], platform, page.name, url, None)
                log.info(f"  -> {url}")
            except Exception as e:
                st.record_post(clip["id"], platform, page.name, None, str(e)[:500])
                log.warning(f"  post failed: {e}")


def pick_clip(st: State, page: str, platform: str):
    for _ in range(20):
        clip = st.next_clip_to_post(page, platform)
        if clip is None:
            return None
        camp = st.db.execute("SELECT data FROM campaigns WHERE url=?", (clip["campaign_url"],)).fetchone()
        platforms = json.loads(camp["data"]).get("platforms", []) if camp else []
        if platform_allowed(platform, platforms) and Path(clip["path"]).exists():
            return clip
        # not allowed for this platform: mark so we don't pick it again
        st.db.execute("INSERT OR REPLACE INTO posts (clip_id, platform, page, status, error, attempts) "
                      "VALUES (?,?,?, 'failed', 'platform not allowed or file missing', 99)",
                      (clip["id"], platform, page))
        st.db.commit()
    return None


def publish(page: Page, platform: str, meta: dict) -> str:
    path = Path(meta["path"])
    if platform == "youtube":
        y = page.youtube
        return uploader.upload_short(path, meta["title"], meta["final_description"], meta["hashtags"],
                                     y.privacy, y.token_file, y.client_secret)
    ig = page.instagram
    caption = f"{meta['title']}\n\n{meta['final_description']}"
    return instagram.post_reel(path, caption, ig.user_id, os.getenv(ig.token_env, ""), ig.graph_version)


# ---------------------------------------------------------------- 4. submit

def submit_due(cfg: BotConfig, st: State) -> None:
    todo = st.posts_to_submit()
    if not todo:
        return
    log.info(f"Submitting {len(todo)} posts on Vyro...")
    with browser(cfg) as b:
        for p in todo:
            page = cfg.page(p["page"])
            try:
                ok, notes = vyro.submit_post(b, cfg, p["campaign_url"], p["url"], p["platform"],
                                             page.handles if page else [])
                st.record_submission(p["clip_id"], p["platform"], ok, None if ok else notes[:500])
                log.info(f"  {'OK' if ok else 'FAILED'} {p['url']} {'' if ok else notes[:150]}")
            except vyro.LoginRequired:
                raise
            except Exception as e:
                st.record_submission(p["clip_id"], p["platform"], False, str(e)[:500])
                log.warning(f"  submit error {p['url']}: {e}")


# ---------------------------------------------------------------- main

def login(cfg: BotConfig) -> None:
    with Browser(cfg.vyro.profile_dir, cfg.vyro.allowed_domains, headless=False) as b:
        b.page.goto(cfg.vyro.start_url)
        input("\nBrowser mein Vyro pe login karo. Login ho jaye to yahan ENTER dabao... ")
    print("Login saved in", cfg.vyro.profile_dir)


def setup_youtube(cfg: BotConfig) -> None:
    for page in cfg.pages:
        if page.youtube and page.youtube.enabled:
            print(f"\n== {page.name}: is page ka YouTube channel choose karo")
            uploader._service(Path(page.youtube.token_file), Path(page.youtube.client_secret))
    print("YouTube connected for all pages.")


def cycle(cfg: BotConfig, st: State, last_scan: float) -> float:
    steps = [make_clips, post_due, submit_due]
    if time.time() - last_scan >= cfg.vyro.scan_every_hours * 3600:
        steps.insert(0, scan)
        last_scan = time.time()
    for step in steps:
        try:
            step(cfg, st)
        except vyro.LoginRequired as e:
            # clipping + posting keep running; only Vyro steps wait for a new login
            log.error(f"{step.__name__}: {e}")
        except Exception:
            log.error(f"{step.__name__} crashed:\n{traceback.format_exc()}")
    log.info(f"Status: {st.summary()}")
    return last_scan


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="bot.yaml")
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--setup-youtube", action="store_true")
    ap.add_argument("--once", action="store_true", help="run one cycle and exit")
    args = ap.parse_args()

    cfg = BotConfig.load(args.config)
    if args.login:
        login(cfg)
        return 0
    if args.setup_youtube:
        setup_youtube(cfg)
        return 0

    setup_logging()
    st = State("bot.db")
    log.info(f"Bot started with {len(cfg.pages)} pages: {', '.join(p.name for p in cfg.pages)}")
    last_scan = 0.0
    while True:
        try:
            last_scan = cycle(cfg, st, last_scan)
        except Exception:
            log.error(f"Cycle crashed:\n{traceback.format_exc()}")
        if args.once:
            return 0
        time.sleep(cfg.loop_minutes * 60)

if __name__ == "__main__":
    sys.exit(main())
