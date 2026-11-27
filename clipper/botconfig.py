"""bot.yaml schema for the 24x7 Vyro bot."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VyroSettings(Strict):
    start_url: str = "https://app.vyro.com"
    allowed_domains: list[str] = ["vyro.com"]
    profile_dir: str = "browser_profile"
    headless: bool = False
    scan_every_hours: float = 3
    max_new_campaigns_per_scan: int = 5
    max_materials_per_campaign: int = 2
    min_cpm_usd: float = 0
    agent_max_steps: int = 30


class NetworkSettings(Strict):
    # VPN guard: Vyro, posting and submitting only run while the internet appears to come
    # from one of these countries (your own VPN app must be connected).
    vpn_required: bool = False
    allowed_countries: list[str] = ["US", "GB", "CA", "AU"]


class TelegramSettings(Strict):
    enabled: bool = False
    chat_id: str = ""            # your chat with the bot (token lives in .env as TELEGRAM_BOT_TOKEN)
    notify_posts: bool = True
    notify_errors: bool = True
    notify_campaigns: bool = True
    notify_summary: bool = True  # daily summary at summary_hour
    summary_hour: int = 21


class YouTubeSettings(Strict):
    enabled: bool = True
    token_file: str
    client_secret: str = "client_secret.json"
    privacy: str = "public"
    max_per_day: int = 3


class InstagramSettings(Strict):
    enabled: bool = True
    user_id: str
    token_env: str  # name of the .env variable holding this page's access token
    graph_version: str = "v23.0"
    max_per_day: int = 3


class Page(Strict):
    name: str
    niche: str
    enabled: bool = True
    language: str = "English"
    clips_per_video: int = 4
    min_gap_minutes: int = 120
    handles: list[str] = []  # your usernames on this page, in case Vyro's form asks for them
    youtube: YouTubeSettings | None = None
    instagram: InstagramSettings | None = None


class BotConfig(Strict):
    vyro: VyroSettings = Field(default_factory=VyroSettings)
    network: NetworkSettings = Field(default_factory=NetworkSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    loop_minutes: int = 10
    pages: list[Page] = []
    clip_defaults: dict = {}  # any Campaign field (crop_mode, whisper_model, captions, ...)

    @classmethod
    def load(cls, path: str | Path = "bot.yaml") -> "BotConfig":
        path = Path(path)
        if not path.exists():
            return cls()
        cfg = cls(**(yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
        if cfg.vyro.start_url.rstrip("/") in ("https://vyro.com", "https://www.vyro.com"):
            cfg.vyro.start_url = "https://app.vyro.com"  # the clipper app lives on app.vyro.com
        return cfg

    def save(self, path: str | Path = "bot.yaml") -> None:
        path = Path(path)
        if path.exists() and not path.with_suffix(".yaml.bak").exists():
            path.with_suffix(".yaml.bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        data = self.model_dump(exclude_none=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        tmp.replace(path)

    def page(self, name: str) -> Page | None:
        return next((p for p in self.pages if p.name == name), None)
