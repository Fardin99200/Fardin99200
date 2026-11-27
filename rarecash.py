"""Rare Cash: web dashboard + bot engine in one program.

    python rarecash.py            # opens http://localhost:8000 in your browser
    python rarecash.py --port 9000 --no-browser
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---- where things live --------------------------------------------------------------
# Source checkout: everything sits next to this file.
# RareCash.exe (PyInstaller): bundled files (web UI, ffmpeg, VPN engine, browser) are in
# sys._MEIPASS; your data (bot.db, bot.yaml, .env, clips, VPN configs) sits next to the exe.
if getattr(sys, "frozen", False):
    for stream in (sys.stdout, sys.stderr):  # Windows console can't print every character
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    APP_DIR = Path(sys.executable).parent.resolve()
    RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)).resolve()
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")  # chromium is bundled inside the package
    for tool_dir in (RES_DIR / "ffmpeg",):
        if tool_dir.exists():
            os.environ["PATH"] = str(tool_dir) + os.pathsep + os.environ.get("PATH", "")
    if (RES_DIR / "vpn_bin" / "wireproxy.exe").exists():
        os.environ.setdefault("RARECASH_WIREPROXY", str(RES_DIR / "vpn_bin" / "wireproxy.exe"))
else:
    APP_DIR = RES_DIR = Path(__file__).parent.resolve()
os.chdir(APP_DIR)
for example, target in (("bot.example.yaml", "bot.example.yaml"), (".env.example", ".env")):
    if not (APP_DIR / target).exists() and (RES_DIR / example).exists():
        shutil.copyfile(RES_DIR / example, APP_DIR / target)

from dotenv import load_dotenv, set_key
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import bot
from clipper import browser_agent, network, vpn
from clipper.botconfig import BotConfig, Page
from clipper.state import State

ROOT = APP_DIR
ENV_FILE = APP_DIR / ".env"
WEB = RES_DIR / "web"
DEFAULT_CPM = 3.0  # $ per 1000 views when a campaign's rate is unknown

engine_stop = threading.Event()
engine: threading.Thread | None = None


def start_engine() -> None:
    global engine
    if engine and engine.is_alive():
        return
    engine_stop.clear()
    engine = threading.Thread(target=bot.run_forever, args=(engine_stop,), daemon=True, name="rarecash-engine")
    engine.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    st = State("bot.db")
    if st.get("vpn_on") == "1" and st.get("vpn_config"):
        threading.Thread(target=lambda: vpn.tunnel.watchdog(True, st.get("vpn_config")), daemon=True).start()
    start_engine()
    yield
    engine_stop.set()
    vpn.tunnel.stop(clear_env=False)


app = FastAPI(title="Rare Cash", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB), name="static")


def db() -> State:
    return State("bot.db")


def cfg() -> BotConfig:
    return BotConfig.load(bot.CONFIG)


def env_set(key: str, value: str) -> None:
    ENV_FILE.touch(exist_ok=True)
    set_key(str(ENV_FILE), key, value)
    os.environ[key] = value


def ts(iso: str | None) -> float | None:
    return datetime.fromisoformat(iso).timestamp() if iso else None


@app.get("/", response_class=HTMLResponse)
def index():
    return (WEB / "index.html").read_text(encoding="utf-8")


# ------------------------------------------------------------------ overview

def campaign_cpm(st: State, campaign_url: str) -> float:
    if bot.is_manual(campaign_url):
        return 0.0
    cpm = st.campaign_data(campaign_url).get("cpm_usd")
    return float(cpm) if cpm else DEFAULT_CPM


def earnings_rows(st: State) -> list[dict]:
    rows = st.db.execute(
        """SELECT p.*, c.meta, c.campaign_url, c.id AS cid FROM posts p JOIN clips c ON c.id=p.clip_id
           WHERE p.status='posted' ORDER BY p.posted_at DESC""").fetchall()
    out = []
    for r in rows:
        cpm = campaign_cpm(st, r["campaign_url"])
        out.append({
            "clip_id": r["clip_id"], "platform": r["platform"], "page": r["page"], "url": r["url"],
            "title": json.loads(r["meta"]).get("title", ""), "views": r["views"] or 0, "likes": r["likes"] or 0,
            "posted_at": ts(r["posted_at"]), "vyro": r["vyro_status"], "cpm": cpm,
            "earned": round((r["views"] or 0) / 1000 * cpm, 2),
        })
    return out


def daily_series(st: State, days: int = 30) -> list[dict]:
    """Per day: views gained, estimated $ earned (views x CPM), posts published."""
    today = datetime.now(timezone.utc).date()
    day_list = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    out = {d: {"day": d, "views": 0, "earned": 0.0, "posts": 0} for d in day_list}
    cpm_cache: dict[int, float] = {}
    rows = st.db.execute(
        "SELECT h.clip_id, h.platform, h.day, h.views, c.campaign_url FROM stats_history h "
        "JOIN clips c ON c.id=h.clip_id ORDER BY h.clip_id, h.platform, h.day").fetchall()
    prev_key, prev_views = None, 0
    for r in rows:
        key = (r["clip_id"], r["platform"])
        if key != prev_key:
            prev_key, prev_views = key, 0
        gained = max(0, r["views"] - prev_views)
        prev_views = r["views"]
        if r["day"] in out:
            if r["clip_id"] not in cpm_cache:
                cpm_cache[r["clip_id"]] = campaign_cpm(st, r["campaign_url"])
            out[r["day"]]["views"] += gained
            out[r["day"]]["earned"] += gained / 1000 * cpm_cache[r["clip_id"]]
    for r in st.db.execute("SELECT substr(posted_at,1,10) AS d, COUNT(*) AS n FROM posts "
                           "WHERE status='posted' GROUP BY d"):
        if r["d"] in out:
            out[r["d"]]["posts"] = r["n"]
    for v in out.values():
        v["earned"] = round(v["earned"], 2)
    return list(out.values())


def warnings(c: BotConfig, st: State) -> list[dict]:
    w = []
    add = lambda level, text, tab=None: w.append({"level": level, "text": text, "tab": tab})
    if not os.getenv("ANTHROPIC_API_KEY"):
        add("critical", "Claude API key nahi hai. Settings mein daalo.", "settings")
    if not shutil.which("ffmpeg"):
        add("critical", "FFmpeg install nahi hai (PowerShell: winget install ffmpeg)", None)
    t = vpn.tunnel.status()
    if st.get("vpn_on") == "1" and t["state"] == "error":
        add("critical", f"Built-in VPN connect nahi ho raha: {t['error']}. Bot Vyro/posting rok ke rakhega.", "settings")
    vpn_s = json.loads(st.get("vpn", "{}") or "{}")
    if c.network.vpn_required and vpn_s and not vpn_s.get("pass", True) and st.get("vpn_on") != "1":
        add("critical", f"VPN band hai: internet {vpn_s.get('country_name') or 'unknown'} se aa raha hai. "
                        "Vyro aur posting ruki hai. VPN app connect karo.", "settings")
    if not c.pages:
        add("warning", "Abhi koi page nahi hai. Pages mein jaake pehla page add karo.", "pages")
    lc = json.loads(st.get("login_check", "{}") or "{}")
    if lc.get("ok") is False:
        add("critical", "Vyro login nahi hua (check fail). Settings → Vyro Login dobara karo.", "settings")
    elif not st.get("login_ok_at"):
        add("warning", "Vyro login abhi tak nahi hua. Settings → 'Vyro Login' dabao.", "settings")
    if st.get("login_required") == "1":
        add("critical", "Vyro login expire ho gaya. Settings → 'Vyro Login' dabao.", "settings")
    missing_secret, not_connected, no_token = {}, [], []
    for p in c.pages:
        if not p.enabled:
            continue
        if p.youtube and p.youtube.enabled:
            if not Path(p.youtube.client_secret).exists():
                missing_secret.setdefault(p.youtube.client_secret, []).append(p.name)
            elif not Path(p.youtube.token_file).exists():
                not_connected.append(p.name)
        if p.instagram and p.instagram.enabled and not os.getenv(p.instagram.token_env):
            no_token.append(p.name)
    for file, names in missing_secret.items():
        add("warning", f"YouTube ke liye {file} nahi mili ({', '.join(names)}). README: YouTube setup", "pages")
    if not_connected:
        add("warning", f"YouTube connect nahi hai: {', '.join(not_connected)}. Pages mein 'Connect' dabao.", "pages")
    if no_token:
        add("warning", f"Instagram token nahi hai: {', '.join(no_token)}. Page edit karke token daalo.", "pages")
    return w


@app.get("/api/overview")
def overview():
    st, c = db(), cfg()
    earn = earnings_rows(st)
    last_scan = float(st.get("last_scan", "0"))
    alive = bool(engine and engine.is_alive())
    since_day = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    q = lambda sql, *a: st.db.execute(sql, a).fetchone()[0]
    return {
        "engine_alive": alive,
        "enabled": st.get("enabled", "1") == "1",
        "status": st.get("status", "Start ho raha hai...") if alive else "Engine band hai (restart karo)",
        "last_cycle": float(st.get("last_cycle", "0")) or None,
        "next_scan": last_scan + c.vyro.scan_every_hours * 3600 if last_scan else None,
        "pages": len([p for p in c.pages if p.enabled]),
        "campaigns_active": q("SELECT COUNT(*) FROM campaigns WHERE status IN ('ready','pending')"),
        "campaigns_total": q("SELECT COUNT(*) FROM campaigns WHERE page!=''"),
        "clips": q("SELECT COUNT(*) FROM clips"),
        "clips_today": q("SELECT COUNT(*) FROM clips WHERE created_at>=?", since_day),
        "posted": q("SELECT COUNT(*) FROM posts WHERE status='posted'"),
        "posted_today": q("SELECT COUNT(*) FROM posts WHERE status='posted' AND posted_at>=?", since_day),
        "submitted": q("SELECT COUNT(*) FROM posts WHERE vyro_status='submitted'"),
        "views": sum(e["views"] for e in earn),
        "earned": round(sum(e["earned"] for e in earn), 2),
        "warnings": warnings(c, st),
        "activity": log_tail(12),
        "vpn": json.loads(st.get("vpn", "{}") or "{}"),
        "vpn_required": c.network.vpn_required,
        "tunnel": {**vpn.tunnel.status(), "wanted": st.get("vpn_on") == "1"},
    }


@app.get("/api/dashboard")
def dashboard():
    st, c = db(), cfg()
    o = overview()
    earn = earnings_rows(st)
    pages = []
    for i, p in enumerate(c.pages):  # color follows the page's position in the config
        mine = [e for e in earn if e["page"] == p.name]
        pages.append({"name": p.name, "slot": i, "enabled": p.enabled, "posts": len(mine),
                      "views": sum(e["views"] for e in mine), "earned": round(sum(e["earned"] for e in mine), 2),
                      "clips": st.db.execute("SELECT COUNT(*) FROM clips WHERE page=?", (p.name,)).fetchone()[0]})
    capacity = 0
    for p in c.pages:
        if p.enabled:
            capacity += sum(p.youtube.max_per_day if pf == "youtube" else p.instagram.max_per_day
                            for pf in bot.page_platforms(p))
    return {**o, "daily": daily_series(st, 30), "by_page": pages, "capacity_today": capacity}


@app.get("/api/network")
def network_check(refresh: bool = False):
    c = cfg()
    v = network.vpn_status(c.network.allowed_countries, c.network.vpn_required, max_age=0 if refresh else 60)
    db().set("vpn", json.dumps(v))
    return v


class Toggle(BaseModel):
    enabled: bool


@app.get("/api/vpn")
def vpn_get():
    st = db()
    return {**vpn.tunnel.status(), "wanted": st.get("vpn_on") == "1", "selected": st.get("vpn_config", ""),
            "configs": vpn.list_configs()}


class VpnIn(BaseModel):
    enabled: bool
    config: str = ""


@app.post("/api/vpn")
def vpn_set(body: VpnIn):
    st = db()
    if body.enabled:
        name = body.config or st.get("vpn_config", "") or next((c["name"] for c in vpn.list_configs()), "")
        if not name:
            raise HTTPException(400, "Pehle VPN server add karo (Settings → VPN → WireGuard config)")
        st.set("vpn_config", name)
        st.set("vpn_on", "1")

        def connect():
            try:
                vpn.tunnel.start(name)
            except Exception:
                pass  # error is shown in the VPN status

        threading.Thread(target=connect, daemon=True).start()
        return {"ok": True, "message": "VPN connect ho raha hai…"}
    st.set("vpn_on", "0")
    vpn.tunnel.stop()
    st.set("vpn", "{}")
    return {"ok": True, "message": "VPN OFF"}


class VpnConfigIn(BaseModel):
    name: str
    text: str


@app.post("/api/vpn/configs")
def vpn_config_add(body: VpnConfigIn):
    try:
        name = vpn.save_config(body.name, body.text)
    except vpn.VPNError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "name": name, "message": f"Server '{name}' add ho gaya"}


@app.delete("/api/vpn/configs/{name}")
def vpn_config_delete(name: str):
    st = db()
    if st.get("vpn_config") == name and st.get("vpn_on") == "1":
        raise HTTPException(400, "Ye server abhi chal raha hai, pehle VPN OFF karo")
    vpn.delete_config(name)
    return {"ok": True}


@app.post("/api/bot")
def bot_toggle(t: Toggle):
    db().set("enabled", "1" if t.enabled else "0")
    start_engine()
    return {"ok": True}


@app.post("/api/bot/run-now")
def bot_run_now():
    db().set("run_now", "1")
    start_engine()
    return {"ok": True}


@app.post("/api/bot/scan-now")
def bot_scan_now():
    st = db()
    st.set("last_scan", "0")
    st.set("run_now", "1")
    return {"ok": True}


class LoginIn(BaseModel):
    mode: str = "bot"   # bot | normal
    link: str = ""      # login link from Vyro's email (optional)


@app.post("/api/vyro/login")
def vyro_login(body: LoginIn | None = None):
    body = body or LoginIn()
    link = body.link.strip()
    if link and not link.startswith("https://"):
        raise HTTPException(400, "Poora login link paste karo (https:// se shuru hota hai)")
    st = db()
    st.set("login_mode", "normal" if body.mode == "normal" else "bot")
    st.set("login_link", link)
    st.set("login_done", "0")
    st.set("login_request", "1")
    start_engine()
    msg = ("Normal browser khulega. Login karke window band karo (ya 'Login ho gaya' dabao)." if body.mode == "normal"
           else "Thodi der mein browser khulega. Vyro pe login karke window band kar do.")
    return {"ok": True, "message": msg}


@app.post("/api/vyro/login-done")
def vyro_login_done():
    db().set("login_done", "1")
    return {"ok": True, "message": "Theek hai, login save karke check kar raha hoon"}


@app.post("/api/vyro/check")
def vyro_check():
    db().set("login_verify", "1")
    start_engine()
    return {"ok": True, "message": "Login check ho raha hai (10-20 second)"}


# ------------------------------------------------------------------ pages

def page_info(p: Page, st: State) -> dict:
    d = p.model_dump()
    d["youtube_connected"] = bool(p.youtube and Path(p.youtube.token_file).exists())
    d["youtube_connecting"] = st.get(f"yt_connect_{p.name}", "")
    d["instagram_token_set"] = bool(p.instagram and os.getenv(p.instagram.token_env))
    for platform in bot.page_platforms(p):
        _, today, limit = bot.next_slot(st, p, platform)
        d[f"{platform}_today"] = f"{today}/{limit}"
    d["clips"] = st.db.execute("SELECT COUNT(*) FROM clips WHERE page=?", (p.name,)).fetchone()[0]
    d["views"] = st.db.execute("SELECT COALESCE(SUM(views),0) FROM posts WHERE page=?", (p.name,)).fetchone()[0]
    return d


@app.get("/api/pages")
def pages_list():
    st = db()
    return [page_info(p, st) for p in cfg().pages]


class PageIn(BaseModel):
    page: Page
    original_name: str | None = None
    instagram_token: str | None = None


@app.post("/api/pages")
def pages_save(body: PageIn):
    c = cfg()
    p = body.page
    p.name = p.name.strip().lower().replace(" ", "_")
    if not p.name:
        raise HTTPException(400, "Page ka naam chahiye")
    if p.youtube and not p.youtube.token_file:
        p.youtube.token_file = f"tokens/youtube_{p.name}.json"
    if p.instagram and not p.instagram.token_env:
        p.instagram.token_env = f"IG_TOKEN_{p.name.upper()}"
    old = body.original_name or p.name
    others = [x for x in c.pages if x.name != old]
    if any(x.name == p.name for x in others):
        raise HTTPException(400, f"'{p.name}' naam ka page pehle se hai")
    idx = next((i for i, x in enumerate(c.pages) if x.name == old), len(c.pages))
    others.insert(idx, p)
    c.pages = others
    c.save(bot.CONFIG)
    if body.instagram_token and p.instagram:
        env_set(p.instagram.token_env, body.instagram_token.strip())
    return {"ok": True}


@app.delete("/api/pages/{name}")
def pages_delete(name: str):
    c = cfg()
    c.pages = [p for p in c.pages if p.name != name]
    c.save(bot.CONFIG)
    return {"ok": True}


@app.post("/api/pages/{name}/toggle")
def pages_toggle(name: str, t: Toggle):
    c = cfg()
    p = c.page(name)
    if not p:
        raise HTTPException(404)
    p.enabled = t.enabled
    c.save(bot.CONFIG)
    return {"ok": True}


@app.post("/api/pages/{name}/youtube-connect")
def pages_youtube_connect(name: str):
    c, st = cfg(), db()
    p = c.page(name)
    if not p or not p.youtube:
        raise HTTPException(404, "Is page pe YouTube set nahi hai")
    if not Path(p.youtube.client_secret).exists():
        raise HTTPException(400, f"{p.youtube.client_secret} nahi mili. README ka 'YouTube setup' dekho.")

    def run():
        s = State("bot.db")
        s.set(f"yt_connect_{name}", "running")
        try:
            bot.setup_youtube(c, only_page=name)
            s.set(f"yt_connect_{name}", "")
        except Exception as e:
            s.set(f"yt_connect_{name}", f"error: {e}")

    threading.Thread(target=run, daemon=True).start()
    return {"ok": True, "message": "Browser mein Google login khulega. Is page ka channel select karo."}


# ------------------------------------------------------------------ campaigns & videos

@app.get("/api/campaigns")
def campaigns_list():
    st = db()
    rows = st.db.execute("SELECT rowid, * FROM campaigns ORDER BY updated_at DESC LIMIT 300").fetchall()
    out = []
    for r in rows:
        data = json.loads(r["data"] or "{}")
        n = st.db.execute("SELECT COUNT(*) FROM clips WHERE campaign_url=?", (r["url"],)).fetchone()[0]
        out.append({"id": r["rowid"], "url": r["url"], "title": r["title"] or data.get("title") or r["url"],
                    "page": r["page"], "status": r["status"], "error": r["error"],
                    "manual": bot.is_manual(r["url"]), "pay": data.get("pay_rate") or "",
                    "cpm": data.get("cpm_usd"), "platforms": data.get("platforms", []),
                    "materials": len(data.get("material_links", [])), "clips": n,
                    "reason": data.get("skip_reason", ""), "updated": ts(r["updated_at"])})
    return out


class CampaignIn(BaseModel):
    url: str
    page: str = ""


@app.post("/api/campaigns")
def campaigns_add(body: CampaignIn):
    st = db()
    url = body.url.strip()
    if not url.startswith("http"):
        raise HTTPException(400, "Poora Vyro campaign link daalo (https://...)")
    if st.campaign_known(url):
        st.update_campaign(url, status="pending", page=body.page or "")
    else:
        st.add_campaign(url, "", {}, body.page, "pending")
    st.set("run_now", "1")
    return {"ok": True}


class StatusIn(BaseModel):
    status: str


@app.post("/api/campaigns/{rowid}/status")
def campaigns_status(rowid: int, body: StatusIn):
    if body.status not in {"ready", "skipped", "pending", "done"}:
        raise HTTPException(400, "bad status")
    st = db()
    row = st.db.execute("SELECT url FROM campaigns WHERE rowid=?", (rowid,)).fetchone()
    if not row:
        raise HTTPException(404)
    st.update_campaign(row["url"], status=body.status)
    return {"ok": True}


class VideoIn(BaseModel):
    video_url: str
    page: str
    title: str = ""
    campaign_url: str = ""


@app.post("/api/videos")
def videos_add(body: VideoIn):
    st, c = db(), cfg()
    if not c.page(body.page):
        raise HTTPException(400, "Page choose karo")
    video = body.video_url.strip()
    if body.campaign_url.strip():
        url = body.campaign_url.strip()
        if st.campaign_known(url):
            data = st.campaign_data(url)
            data["material_links"] = list(dict.fromkeys(data.get("material_links", []) + [video]))
            st.update_campaign(url, data=data, page=body.page, status="ready")
        else:  # bot will open the campaign, join it and read its rules first
            st.add_campaign(url, body.title, {"material_links": [video]}, body.page, "pending")
    else:
        url = f"manual:{uuid.uuid4().hex[:10]}"
        st.add_campaign(url, body.title or Path(video).name or video,
                        {"title": body.title, "material_links": [video], "platforms": []}, body.page, "ready")
    st.set("run_now", "1")
    return {"ok": True}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    dest_dir = ROOT / "uploads"
    dest_dir.mkdir(exist_ok=True)
    name = Path(file.filename or "video.mp4").name
    dest = dest_dir / f"{uuid.uuid4().hex[:6]}_{name}"
    with dest.open("wb") as f:
        while chunk := await file.read(8 * 1024 * 1024):
            f.write(chunk)
    return {"path": str(dest)}


# ------------------------------------------------------------------ clips

@app.get("/api/clips")
def clips_list(page: str = "", limit: int = 200):
    st = db()
    sql = "SELECT * FROM clips" + (" WHERE page=?" if page else "") + " ORDER BY created_at DESC LIMIT ?"
    rows = st.db.execute(sql, ((page,) if page else ()) + (limit,)).fetchall()
    out = []
    for r in rows:
        meta = json.loads(r["meta"])
        posts = {p["platform"]: p for p in st.db.execute("SELECT * FROM posts WHERE clip_id=?", (r["id"],))}
        camp = st.db.execute("SELECT title FROM campaigns WHERE url=?", (r["campaign_url"],)).fetchone()
        out.append({
            "id": r["id"], "page": r["page"], "title": meta.get("title", ""), "score": r["virality"],
            "reason": meta.get("reason", ""), "duration": round(meta.get("end", 0) - meta.get("start", 0)),
            "description": meta.get("final_description", ""), "campaign": camp["title"] if camp else "",
            "status": r["status"], "created": ts(r["created_at"]), "exists": Path(r["path"]).exists(),
            "posts": {k: {"status": v["status"], "url": v["url"], "views": v["views"], "error": v["error"],
                          "vyro": v["vyro_status"], "vyro_error": v["vyro_error"]} for k, v in posts.items()},
        })
    return out


def clip_row(cid: int):
    row = db().db.execute("SELECT * FROM clips WHERE id=?", (cid,)).fetchone()
    if not row:
        raise HTTPException(404)
    return row


@app.post("/api/clips/{cid}/skip")
def clip_skip(cid: int, t: Toggle):
    clip_row(cid)
    st = db()
    st.db.execute("UPDATE clips SET status=? WHERE id=?", ("skipped" if t.enabled else "active", cid))
    st.db.commit()
    return {"ok": True}


@app.post("/api/clips/{cid}/priority")
def clip_priority(cid: int):
    clip_row(cid)
    st = db()
    st.db.execute("UPDATE clips SET virality=100, status='active' WHERE id=?", (cid,))
    st.db.commit()
    return {"ok": True}


@app.get("/media/clip/{cid}")
def media_clip(cid: int):
    return FileResponse(clip_row(cid)["path"], media_type="video/mp4")


@app.get("/media/thumb/{cid}")
def media_thumb(cid: int):
    path = Path(clip_row(cid)["path"])
    thumb = path.parent / ".thumbs" / (path.stem + ".jpg")
    if not thumb.exists():
        thumb.parent.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", str(path), "-frames:v", "1",
                        "-vf", "scale=360:-2", str(thumb)], check=False)
    if not thumb.exists():
        raise HTTPException(404)
    return FileResponse(thumb, media_type="image/jpeg")


# ------------------------------------------------------------------ schedule & earnings

@app.get("/api/schedule")
def schedule():
    st, c = db(), cfg()
    slots = []
    for p in c.pages:
        if not p.enabled:
            continue
        for platform in bot.page_platforms(p):
            when, today, limit = bot.next_slot(st, p, platform)
            queue = st.queue(p.name, platform, limit=5)
            slots.append({
                "page": p.name, "platform": platform, "next_at": when, "today": today, "limit": limit,
                "gap": p.min_gap_minutes, "queue_len": len(st.queue(p.name, platform, limit=1000)),
                "next": [{"id": q["id"], "title": json.loads(q["meta"]).get("title", ""), "score": q["virality"]}
                         for q in queue],
            })
    last_scan = float(st.get("last_scan", "0"))
    recent = st.db.execute(
        "SELECT p.*, c.meta FROM posts p JOIN clips c ON c.id=p.clip_id WHERE p.status='posted' "
        "ORDER BY posted_at DESC LIMIT 15").fetchall()
    return {
        "slots": sorted(slots, key=lambda s: (s["queue_len"] == 0, s["next_at"])),
        "enabled": st.get("enabled", "1") == "1",
        "next_scan": last_scan + c.vyro.scan_every_hours * 3600 if last_scan else time.time(),
        "scan_every_hours": c.vyro.scan_every_hours, "loop_minutes": c.loop_minutes,
        "recent": [{"page": r["page"], "platform": r["platform"], "url": r["url"], "at": ts(r["posted_at"]),
                    "title": json.loads(r["meta"]).get("title", ""), "vyro": r["vyro_status"]} for r in recent],
    }


@app.get("/api/earnings")
def earnings(days: int = 14):
    st = db()
    rows = earnings_rows(st)
    by_page: dict[str, dict] = {}
    for r in rows:
        b = by_page.setdefault(r["page"], {"page": r["page"], "views": 0, "earned": 0.0, "posts": 0})
        b["views"] += r["views"]
        b["earned"] = round(b["earned"] + r["earned"], 2)
        b["posts"] += 1

    series = daily_series(st, days)
    return {
        "total_views": sum(r["views"] for r in rows),
        "total_earned": round(sum(r["earned"] for r in rows), 2),
        "default_cpm": DEFAULT_CPM,
        "by_page": sorted(by_page.values(), key=lambda b: -b["earned"]),
        "daily": series,
        "top": sorted(rows, key=lambda r: -r["views"])[:25],
    }


# ------------------------------------------------------------------ logs & settings

def log_tail(n: int = 200) -> list[str]:
    path = ROOT / "logs" / "bot.log"
    if not path.exists():
        return []
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 200_000))
        lines = f.read().decode("utf-8", "replace").splitlines()
    return lines[-n:]


@app.get("/api/logs")
def logs(lines: int = 300):
    return {"lines": log_tail(lines)}


CLIP_KEYS = ["crop_mode", "captions", "caption_uppercase", "caption_highlight_color", "whisper_model",
             "min_seconds", "max_seconds"]


@app.get("/api/settings")
def settings_get():
    c = cfg()
    from clipper.config import Campaign
    d = Campaign()
    return {
        "vyro": c.vyro.model_dump(),
        "network": c.network.model_dump(),
        "loop_minutes": c.loop_minutes,
        "clip": {k: c.clip_defaults.get(k, getattr(d, k)) for k in CLIP_KEYS},
        "api_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
        "client_secret_found": Path("client_secret.json").exists(),
        "vyro_logged_in": bool(db().get("login_ok_at")) and db().get("login_required") != "1",
        "login_check": json.loads(db().get("login_check", "{}") or "{}"),
        "system_browser": (browser_agent.system_browser() or ("bundled", ""))[0],
    }


class SettingsIn(BaseModel):
    vyro: dict | None = None
    network: dict | None = None
    loop_minutes: int | None = None
    clip: dict | None = None
    api_key: str | None = None


@app.post("/api/settings")
def settings_save(body: SettingsIn):
    c = cfg()
    if body.vyro:
        c.vyro = c.vyro.model_copy(update={k: v for k, v in body.vyro.items() if k in c.vyro.model_fields})
        c.vyro = type(c.vyro)(**c.vyro.model_dump())  # re-validate
    if body.network is not None:
        net = {**c.network.model_dump(), **body.network}
        net["allowed_countries"] = [x.strip().upper() for x in net.get("allowed_countries", []) if x.strip()]
        c.network = type(c.network)(**net)
    if body.loop_minutes:
        c.loop_minutes = max(1, body.loop_minutes)
    if body.clip:
        c.clip_defaults.update({k: v for k, v in body.clip.items() if k in CLIP_KEYS})
    c.save(bot.CONFIG)
    if body.api_key:
        env_set("ANTHROPIC_API_KEY", body.api_key.strip())
    return {"ok": True}


def selftest() -> int:
    """Used by the Windows build to prove the packaged exe works. Prints one line per check."""
    results = []

    def check(name, fn):
        try:
            detail = fn()
            results.append(True)
            print(f"  OK    {name}" + (f"  ({detail})" if detail else ""))
        except Exception as e:
            results.append(False)
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")

    def ffmpeg():
        out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True).stdout
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
        return out.split("\n")[0][:60]

    def render():
        import tempfile
        from clipper import render as r
        from clipper.config import Campaign
        d = Path(tempfile.mkdtemp())
        src = d / "src.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
                        "-f", "lavfi", "-i", "sine", "-t", "3", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(src)],
                       check=True)
        words = [{"start": 0.2 + i * 0.4, "end": 0.5 + i * 0.4, "word": w} for i, w in enumerate("rare cash test ok".split())]
        out = r.render_clip(src, 0, 2.5, [{"start": 0, "end": 2, "text": "", "words": words}], d / "clip.mp4",
                            Campaign(crop_mode="face"))
        w, h, _ = r.probe(out)
        assert (w, h) == (1080, 1920), (w, h)
        return f"{w}x{h} with captions"

    def whisper():
        import faster_whisper  # noqa: F401
        import ctranslate2
        return f"ctranslate2 {ctranslate2.__version__}"

    def opencv():
        import cv2
        c = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        assert not c.empty(), "face model missing"
        return cv2.__version__

    def browser():
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            pg = b.new_page()
            pg.set_content("<title>ok</title>")
            t = pg.title()
            b.close()
        assert t == "ok"
        return "chromium launches"

    def youtube_api():
        from googleapiclient.discovery import build
        build("youtube", "v3", developerKey="selftest", static_discovery=True)
        return "discovery docs bundled"

    def vpn_engine():
        exe = vpn.binary_path()
        assert exe.exists(), f"{exe} missing"
        out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=20)
        return (out.stdout or out.stderr).strip()[:40]

    def web_ui():
        assert (WEB / "index.html").exists() and (WEB / "app.js").exists()
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            assert client.get("/").status_code == 200
            assert client.get("/api/overview").status_code == 200
        engine_stop.set()
        return "dashboard + API respond"

    print("Rare Cash self-test")
    for name, fn in [("ffmpeg", ffmpeg), ("video render", render), ("whisper", whisper), ("opencv face", opencv),
                     ("browser", browser), ("youtube api", youtube_api), ("vpn engine", vpn_engine), ("dashboard", web_ui)]:
        check(name, fn)
    print("ALL OK" if all(results) else "SOME CHECKS FAILED")
    return 0 if all(results) else 1


def main() -> None:
    import uvicorn

    load_dotenv(ENV_FILE)
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="check that every part works, then exit")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    url = f"http://localhost:{args.port}"
    print(f"\n  Rare Cash dashboard: {url}\n  (band karne ke liye ye window band karo ya Ctrl+C)\n")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
