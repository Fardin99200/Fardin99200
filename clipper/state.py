"""SQLite state shared by the bot and the Rare Cash dashboard."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    url TEXT PRIMARY KEY,
    title TEXT,
    data TEXT,             -- JSON from the Vyro scan (+ details)
    page TEXT,             -- which of our pages it was routed to ('' = skipped)
    status TEXT,           -- pending | ready | done | skipped | failed
    error TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS materials (
    url TEXT,
    campaign_url TEXT,
    status TEXT,           -- done | failed
    error TEXT,
    PRIMARY KEY (url, campaign_url)
);
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_url TEXT,
    page TEXT,
    path TEXT UNIQUE,
    meta TEXT,
    virality INTEGER,
    created_at TEXT,
    status TEXT DEFAULT 'active'   -- active | skipped
);
CREATE TABLE IF NOT EXISTS posts (
    clip_id INTEGER,
    platform TEXT,         -- youtube | instagram
    page TEXT,
    url TEXT,
    status TEXT,           -- posted | failed
    error TEXT,
    attempts INTEGER DEFAULT 0,
    posted_at TEXT,
    vyro_status TEXT,      -- NULL | submitted | failed | not_needed
    vyro_error TEXT,
    vyro_attempts INTEGER DEFAULT 0,
    platform_id TEXT,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    stats_at TEXT,
    PRIMARY KEY (clip_id, platform)
);
CREATE TABLE IF NOT EXISTS stats_history (
    clip_id INTEGER,
    platform TEXT,
    day TEXT,
    views INTEGER,
    PRIMARY KEY (clip_id, platform, day)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

# columns added after the first release (ALTER TABLE for old databases)
MIGRATIONS = [
    ("clips", "status", "TEXT DEFAULT 'active'"),
    ("posts", "platform_id", "TEXT"),
    ("posts", "views", "INTEGER DEFAULT 0"),
    ("posts", "likes", "INTEGER DEFAULT 0"),
    ("posts", "stats_at", "TEXT"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class State:
    def __init__(self, path: str | Path = "bot.db"):
        self.db = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        for table, col, decl in MIGRATIONS:
            cols = {r["name"] for r in self.db.execute(f"PRAGMA table_info({table})")}
            if col not in cols:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        self.db.commit()

    # settings / control
    def get(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value) -> None:
        self.db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, str(value)))
        self.db.commit()

    # campaigns
    def campaign_known(self, url: str) -> bool:
        return self.db.execute("SELECT 1 FROM campaigns WHERE url=?", (url,)).fetchone() is not None

    def add_campaign(self, url: str, title: str, data: dict, page: str, status: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO campaigns VALUES (?,?,?,?,?,?,?,?)",
            (url, title, json.dumps(data, ensure_ascii=False), page, status, None, now(), now()),
        )
        self.db.commit()

    def update_campaign(self, url: str, **fields) -> None:
        if "data" in fields:
            fields["data"] = json.dumps(fields["data"], ensure_ascii=False)
        sets = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE campaigns SET {sets}, updated_at=? WHERE url=?", (*fields.values(), now(), url))
        self.db.commit()

    def campaigns(self, status: str) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM campaigns WHERE status=? ORDER BY created_at", (status,)).fetchall()

    def campaign_data(self, url: str) -> dict:
        row = self.db.execute("SELECT data FROM campaigns WHERE url=?", (url,)).fetchone()
        return json.loads(row["data"]) if row else {}

    # materials
    def material_done(self, url: str, campaign_url: str) -> bool:
        return self.db.execute(
            "SELECT 1 FROM materials WHERE url=? AND campaign_url=?", (url, campaign_url)).fetchone() is not None

    def mark_material(self, url: str, campaign_url: str, status: str, error: str | None = None) -> None:
        self.db.execute("INSERT OR REPLACE INTO materials VALUES (?,?,?,?)", (url, campaign_url, status, error))
        self.db.commit()

    # clips
    def add_clip(self, campaign_url: str, page: str, meta: dict) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO clips (campaign_url, page, path, meta, virality, created_at) VALUES (?,?,?,?,?,?)",
            (campaign_url, page, meta["path"], json.dumps(meta, ensure_ascii=False), meta.get("virality_score", 0), now()),
        )
        self.db.commit()

    def queue(self, page: str, platform: str, max_attempts: int = 3, limit: int = 20) -> list[sqlite3.Row]:
        """Clips of this page waiting to be posted on this platform, best first."""
        return self.db.execute(
            """SELECT c.* FROM clips c
               LEFT JOIN posts p ON p.clip_id=c.id AND p.platform=?
               WHERE c.page=? AND c.status='active'
                 AND (p.clip_id IS NULL OR (p.status='failed' AND p.attempts<?))
               ORDER BY c.virality DESC, c.created_at ASC LIMIT ?""",
            (platform, page, max_attempts, limit),
        ).fetchall()

    def next_clip_to_post(self, page: str, platform: str, max_attempts: int = 3) -> sqlite3.Row | None:
        rows = self.queue(page, platform, max_attempts, 1)
        return rows[0] if rows else None

    # posts
    def record_post(self, clip_id: int, platform: str, page: str, url: str | None, error: str | None,
                    platform_id: str | None = None, vyro_status: str | None = None) -> None:
        status = "posted" if url else "failed"
        self.db.execute(
            """INSERT INTO posts (clip_id, platform, page, url, status, error, attempts, posted_at, platform_id, vyro_status)
               VALUES (?,?,?,?,?,?,1,?,?,?)
               ON CONFLICT(clip_id, platform) DO UPDATE SET
                 url=excluded.url, status=excluded.status, error=excluded.error, platform_id=excluded.platform_id,
                 vyro_status=excluded.vyro_status, attempts=posts.attempts+1, posted_at=excluded.posted_at""",
            (clip_id, platform, page, url, status, error, now(), platform_id, vyro_status),
        )
        self.db.commit()

    def posts_since(self, page: str, platform: str, hours: float) -> list[sqlite3.Row]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
        return self.db.execute(
            "SELECT * FROM posts WHERE page=? AND platform=? AND status='posted' AND posted_at>=? ORDER BY posted_at DESC",
            (page, platform, since),
        ).fetchall()

    def posts_to_submit(self, min_age_minutes: int = 10, max_attempts: int = 3) -> list[sqlite3.Row]:
        before = (datetime.now(timezone.utc) - timedelta(minutes=min_age_minutes)).isoformat(timespec="seconds")
        return self.db.execute(
            """SELECT p.*, c.campaign_url, c.meta FROM posts p JOIN clips c ON c.id=p.clip_id
               WHERE p.status='posted' AND p.posted_at<=?
                 AND (p.vyro_status IS NULL OR (p.vyro_status='failed' AND p.vyro_attempts<?))""",
            (before, max_attempts),
        ).fetchall()

    def record_submission(self, clip_id: int, platform: str, ok: bool, error: str | None = None) -> None:
        self.db.execute(
            "UPDATE posts SET vyro_status=?, vyro_error=?, vyro_attempts=vyro_attempts+1 WHERE clip_id=? AND platform=?",
            ("submitted" if ok else "failed", error, clip_id, platform),
        )
        self.db.commit()

    def posts_for_stats(self, days: int = 30) -> list[sqlite3.Row]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        return self.db.execute(
            "SELECT * FROM posts WHERE status='posted' AND platform_id IS NOT NULL AND posted_at>=?", (since,)
        ).fetchall()

    def record_stats(self, clip_id: int, platform: str, views: int, likes: int) -> None:
        self.db.execute("UPDATE posts SET views=?, likes=?, stats_at=? WHERE clip_id=? AND platform=?",
                        (views, likes, now(), clip_id, platform))
        self.db.execute("INSERT OR REPLACE INTO stats_history VALUES (?,?,?,?)",
                        (clip_id, platform, datetime.now(timezone.utc).date().isoformat(), views))
        self.db.commit()

    def summary(self) -> dict:
        q = lambda sql: self.db.execute(sql).fetchone()[0]
        return {
            "campaigns": q("SELECT COUNT(*) FROM campaigns WHERE page!=''"),
            "clips": q("SELECT COUNT(*) FROM clips"),
            "posted": q("SELECT COUNT(*) FROM posts WHERE status='posted'"),
            "submitted": q("SELECT COUNT(*) FROM posts WHERE vyro_status='submitted'"),
        }
