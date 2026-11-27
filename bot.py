"""Rare Cash bot engine (24x7).

Loop: scan Vyro campaigns -> route to niche pages -> join + read material -> make clips ->
post on YouTube Shorts / Instagram Reels (rate-limited per page) -> submit post links on Vyro ->
refresh views for analytics.

Usually started by the dashboard (python rarecash.py). Standalone use:
    python bot.py --login          # one time: log in to Vyro in the bot's browser
    python bot.py --setup-youtube  # one time: connect each page's YouTube channel
    python bot.py                  # run forever without the dashboard
    python bot.py --once           # one cycle (for testing)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from clipper import instagram, network, pipeline, uploader, vpn, vyro
from clipper.botconfig import BotConfig, Page
from clipper.browser_agent import Browser
from clipper.config import Campaign
from clipper.state import State

log = logging.getLogger("bot")
OUT = Path("output")
CONFIG = "bot.yaml"
STATS_EVERY_HOURS = 2


def setup_logging() -> None:
    if log.handlers:
        return
    Path("logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler("logs/bot.log", encoding="utf-8")):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def status(st: State, text: str) -> None:
    st.set("status", text)
    st.set("heartbeat", time.time())


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


def is_manual(campaign_url: str) -> bool:
    return campaign_url.startswith("manual:")


# ---------------------------------------------------------------- 1. scan

def scan(cfg: BotConfig, st: State) -> None:
    active = cfg.model_copy(update={"pages": [p for p in cfg.pages if p.enabled]})
    pending = st.campaigns("pending")  # Vyro links you added in the dashboard
    if not active.pages and not pending:
        return
    status(st, "Vyro pe naye campaigns dhundh raha hai")
    log.info("Scanning Vyro campaigns...")
    with browser(cfg) as b:
        for row in pending:
            read_campaign(b, cfg, st, row["url"], row["title"] or "", json.loads(row["data"]), row["page"], active)

        if not active.pages:
            return
        found = vyro.scan_campaigns(b, active)
        log.info(f"  {len(found)} campaigns on Vyro")
        new = [c for c in found if c.get("url") and not st.campaign_known(c["url"])]
        if not new:
            return
        routes = {r.url: r for r in vyro.route_campaigns(new, active)}
        accepted = 0
        for c in new:
            r = routes.get(c["url"])
            page = r.page if r and active.page(r.page) else ""
            c["cpm_usd"] = r.cpm_usd if r else None
            cpm_ok = c["cpm_usd"] is None or c["cpm_usd"] >= cfg.vyro.min_cpm_usd
            usable = page and cpm_ok and any(platform_allowed(p, c.get("platforms") or [])
                                             for p in page_platforms(active.page(page)))
            if not usable:
                st.add_campaign(c["url"], c.get("title", ""), {**c, "skip_reason": r.reason if r else "no match"}, "", "skipped")
                log.info(f"  skip: {c.get('title')} ({r.reason if r else 'no route'})")
                continue
            if accepted >= cfg.vyro.max_new_campaigns_per_scan:
                continue  # left unknown, so the next scan picks it up
            if read_campaign(b, cfg, st, c["url"], c.get("title", ""), c, page):
                accepted += 1


def read_campaign(b: Browser, cfg: BotConfig, st: State, url: str, title: str, data: dict, page: str,
                  active: BotConfig | None = None) -> bool:
    try:
        details = vyro.campaign_details(b, cfg, url)
    except vyro.LoginRequired:
        raise
    except Exception as e:
        log.warning(f"  could not open {title or url}: {e}")
        if st.campaign_known(url):
            st.update_campaign(url, status="failed", error=str(e)[:500])
        return False
    merged = {**data, **details}
    merged["material_links"] = list(dict.fromkeys(data.get("material_links", []) + details.get("material_links", [])))
    if not page and active and active.pages:  # added from the dashboard without choosing a page
        summary = {"url": url, "title": title, "platforms": merged.get("platforms", []),
                   "summary": (merged.get("rules") or "")[:800]}
        r = next(iter(vyro.route_campaigns([summary], active)), None)
        page = r.page if r and active.page(r.page) else ""
        merged["cpm_usd"] = r.cpm_usd if r else None
    ok = details.get("active", True) and merged["material_links"] and page
    new_status = "ready" if ok else "skipped"
    if st.campaign_known(url):
        st.update_campaign(url, data=merged, page=page or "", status=new_status, title=title or details.get("title", ""))
    else:
        st.add_campaign(url, title, merged, page if ok else "", new_status)
    log.info(f"  {'+' if ok else 'skip'} {title or url} -> page '{page}' ({len(merged['material_links'])} links)")
    return bool(ok)


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
    ready = [r for r in st.campaigns("ready") if (cfg.page(r["page"]) and cfg.page(r["page"]).enabled)]
    if not ready:
        return
    row = ready[0]
    data, page = json.loads(row["data"]), cfg.page(row["page"])
    c = campaign_settings(cfg, page, data)
    log.info(f"Making clips for '{row['title']}' (page {page.name})")
    links = [u for u in data.get("material_links", []) if not st.material_done(u, row["url"])]
    for link in links[: cfg.vyro.max_materials_per_campaign]:
        status(st, f"Clips bana raha hai: {row['title'][:60]}")
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

def next_slot(st: State, page: Page, platform: str) -> tuple[float, int, int]:
    """(epoch seconds when the next post is allowed, posts in last 24h, daily limit)."""
    limit = page.youtube.max_per_day if platform == "youtube" else page.instagram.max_per_day
    recent = st.posts_since(page.name, platform, 24)
    t = time.time()
    if recent:
        last = datetime.fromisoformat(recent[0]["posted_at"]).timestamp()
        t = max(t, last + page.min_gap_minutes * 60)
    if len(recent) >= limit:
        oldest = datetime.fromisoformat(recent[limit - 1]["posted_at"]).timestamp()
        t = max(t, oldest + 24 * 3600)
    return t, len(recent), limit


def post_due(cfg: BotConfig, st: State) -> None:
    for page in cfg.pages:
        if not page.enabled:
            continue
        for platform in page_platforms(page):
            when, _, _ = next_slot(st, page, platform)
            if when > time.time():
                continue
            clip = pick_clip(st, page.name, platform)
            if clip is None:
                continue
            if not vpn_check(cfg, st):  # VPN dropped in the middle of the round
                return
            meta = json.loads(clip["meta"])
            status(st, f"Post kar raha hai: {page.name} / {platform}")
            log.info(f"Posting to {page.name}/{platform}: {meta['title']}")
            try:
                url, pid = publish(page, platform, meta)
                st.record_post(clip["id"], platform, page.name, url, None, pid,
                               "not_needed" if is_manual(clip["campaign_url"]) else None)
                log.info(f"  -> {url}")
            except Exception as e:
                st.record_post(clip["id"], platform, page.name, None, str(e)[:500])
                log.warning(f"  post failed: {e}")


def pick_clip(st: State, page: str, platform: str):
    for clip in st.queue(page, platform):
        platforms = st.campaign_data(clip["campaign_url"]).get("platforms", [])
        if platform_allowed(platform, platforms) and Path(clip["path"]).exists():
            return clip
        # not allowed for this platform: mark so we don't pick it again
        st.db.execute("INSERT OR REPLACE INTO posts (clip_id, platform, page, status, error, attempts) "
                      "VALUES (?,?,?, 'failed', 'platform not allowed or file missing', 99)",
                      (clip["id"], platform, page))
        st.db.commit()
    return None


def publish(page: Page, platform: str, meta: dict) -> tuple[str, str]:
    """Returns (public url, platform's own id)."""
    path = Path(meta["path"])
    if platform == "youtube":
        y = page.youtube
        url = uploader.upload_short(path, meta["title"], meta["final_description"], meta["hashtags"],
                                    y.privacy, y.token_file, y.client_secret)
        return url, uploader.video_id(url)
    ig = page.instagram
    caption = f"{meta['title']}\n\n{meta['final_description']}"
    return instagram.post_reel(path, caption, ig.user_id, os.getenv(ig.token_env, ""), ig.graph_version)


# ---------------------------------------------------------------- 4. submit

def submit_due(cfg: BotConfig, st: State) -> None:
    todo = [p for p in st.posts_to_submit() if not is_manual(p["campaign_url"])]
    if not todo:
        return
    status(st, f"Vyro pe {len(todo)} links submit kar raha hai")
    log.info(f"Submitting {len(todo)} posts on Vyro...")
    with browser(cfg) as b:
        for p in todo:
            if not vpn_check(cfg, st):
                return
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


# ---------------------------------------------------------------- 5. analytics

def refresh_stats(cfg: BotConfig, st: State) -> None:
    if time.time() - float(st.get("last_stats", "0")) < STATS_EVERY_HOURS * 3600:
        return
    st.set("last_stats", time.time())
    posts = st.posts_for_stats()
    if not posts:
        return
    status(st, "Views update kar raha hai")
    for page in cfg.pages:
        mine = [p for p in posts if p["page"] == page.name]
        yt = [p for p in mine if p["platform"] == "youtube"]
        if yt and page.youtube:
            try:
                stats = uploader.get_stats([p["platform_id"] for p in yt], page.youtube.token_file,
                                           page.youtube.client_secret)
                for p in yt:
                    if p["platform_id"] in stats:
                        st.record_stats(p["clip_id"], "youtube", *stats[p["platform_id"]])
            except Exception as e:
                log.warning(f"YouTube stats failed for {page.name}: {e}")
        if page.instagram:
            token = os.getenv(page.instagram.token_env, "")
            for p in (p for p in mine if p["platform"] == "instagram"):
                try:
                    st.record_stats(p["clip_id"], "instagram",
                                    *instagram.get_stats(p["platform_id"], token, page.instagram.graph_version))
                except Exception as e:
                    log.warning(f"Instagram stats failed for {p['url']}: {e}")


# ---------------------------------------------------------------- control

def login(cfg: BotConfig, st: State | None = None) -> None:
    """Open the bot's browser on Vyro; the login is saved when you close the window."""
    if st:
        status(st, "Vyro login window khuli hai: login karke window band karo")
    print("Browser mein Vyro pe login karo, phir browser window band kar do.")
    try:
        with Browser(cfg.vyro.profile_dir, cfg.vyro.allowed_domains, headless=False) as b:
            b.page.goto(cfg.vyro.start_url)
            b.ctx.wait_for_event("close", timeout=0)
    except Exception as e:
        if "closed" not in str(e).lower():
            raise
    st = st or State("bot.db")
    st.set("login_ok_at", time.time())
    st.set("login_required", "0")
    log.info("Vyro login saved")


def setup_youtube(cfg: BotConfig, only_page: str | None = None) -> None:
    for page in cfg.pages:
        if page.youtube and page.youtube.enabled and (only_page is None or page.name == only_page):
            print(f"\n== {page.name}: is page ka YouTube channel choose karo")
            uploader._service(Path(page.youtube.token_file), Path(page.youtube.client_secret))


NEEDS_VPN = {"scan", "post_due", "submit_due"}


def vpn_wanted(st: State) -> bool:
    return st.get("vpn_on") == "1"


def vpn_check(cfg: BotConfig, st: State) -> bool:
    if vpn_wanted(st) and vpn.tunnel.status()["state"] != "on":
        st.set("vpn", json.dumps({"pass": False, "country_name": "VPN connect nahi", "country": "",
                                  "required": True, "ip": ""}))
        return False
    v = network.vpn_status(cfg.network.allowed_countries, cfg.network.vpn_required or vpn_wanted(st))
    st.set("vpn", json.dumps(v))
    return v["pass"]


def cycle(cfg: BotConfig, st: State) -> None:
    steps = [make_clips, post_due, submit_due, refresh_stats]
    if time.time() - float(st.get("last_scan", "0")) >= cfg.vyro.scan_every_hours * 3600 or st.campaigns("pending"):
        steps.insert(0, scan)
        st.set("last_scan", time.time())
    vpn_warned = False
    for step in steps:
        if step.__name__ in NEEDS_VPN and not vpn_check(cfg, st):
            if not vpn_warned:
                v = json.loads(st.get("vpn", "{}"))
                where = v.get("country_name") or "unknown"
                log.warning(f"VPN guard: internet {where} se aa raha hai (allowed: {', '.join(cfg.network.allowed_countries)}). "
                            "Vyro/posting ruki hai, sirf clips ban rahe hain.")
                status(st, f"VPN band hai ({where}): Vyro aur posting ruki hai")
                vpn_warned = True
            continue
        try:
            step(cfg, st)
        except vyro.LoginRequired as e:
            # clipping + posting keep running; only Vyro steps wait for a new login
            st.set("login_required", "1")
            log.error(f"{step.__name__}: {e}")
        except Exception:
            log.error(f"{step.__name__} crashed:\n{traceback.format_exc()}")
    st.set("last_cycle", time.time())
    log.info(f"Status: {st.summary()}")


def run_forever(stop: threading.Event | None = None, once: bool = False) -> None:
    """Main loop. Reads on/off, run-now and login requests from the dashboard via the DB."""
    setup_logging()
    stop = stop or threading.Event()
    st = State("bot.db")
    log.info("Rare Cash bot engine started")
    last_vpn = 0.0
    while not stop.is_set():
        if time.time() - last_vpn > 20:  # keep the built-in VPN up while it's switched ON
            vpn.tunnel.watchdog(vpn_wanted(st), st.get("vpn_config", ""))
            last_vpn = time.time()
        try:
            cfg = BotConfig.load(CONFIG)
        except Exception as e:
            status(st, f"bot.yaml mein galti hai: {e}")
            stop.wait(30)
            continue

        if st.get("login_request") == "1":
            st.set("login_request", "0")
            try:
                login(cfg, st)
                st.set("login_required", "0")
            except Exception as e:
                log.error(f"Login failed: {e}")

        if st.get("enabled", "1") == "1" or st.get("run_now") == "1" or once:
            st.set("run_now", "0")
            try:
                cycle(cfg, st)
            except Exception:
                log.error(f"Cycle crashed:\n{traceback.format_exc()}")
            if once:
                return
            wake = time.time() + cfg.loop_minutes * 60
            status(st, f"Aaram: agla round {datetime.fromtimestamp(wake).strftime('%H:%M')} pe")
        else:
            wake = time.time() + 5
            status(st, "Bot OFF hai")

        while time.time() < wake and not stop.is_set():
            if st.get("run_now") == "1" or st.get("login_request") == "1":
                break
            if st.get("enabled", "1") == "0" and not st.get("status", "").startswith("Bot OFF"):
                status(st, "Bot OFF hai")
            st.set("heartbeat", time.time())
            stop.wait(2)


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--setup-youtube", action="store_true")
    ap.add_argument("--once", action="store_true", help="run one cycle and exit")
    args = ap.parse_args()

    cfg = BotConfig.load(CONFIG)
    if args.login:
        login(cfg)
        return 0
    if args.setup_youtube:
        setup_youtube(cfg)
        return 0
    run_forever(once=args.once)
    return 0


if __name__ == "__main__":
    sys.exit(main())
