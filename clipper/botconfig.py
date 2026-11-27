"""bot.yaml schema for the 24x7 Vyro bot."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VyroSettings(Strict):
    start_url: str = "https://vyro.com"
    allowed_domains: list[str] = ["vyro.com"]
    profile_dir: str = "browser_profile"
    headless: bool = False
    scan_every_hours: float = 3
    max_new_campaigns_per_scan: int = 5
    max_materials_per_campaign: int = 2
    min_cpm_usd: float = 0
    agent_max_steps: int = 30


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
    language: str = "English"
    clips_per_video: int = 4
    min_gap_minutes: int = 120
    handles: list[str] = []  # your usernames on this page, in case Vyro's form asks for them
    youtube: YouTubeSettings | None = None
    instagram: InstagramSettings | None = None


class BotConfig(Strict):
    vyro: VyroSettings = Field(default_factory=VyroSettings)
    loop_minutes: int = 10
    pages: list[Page]
    clip_defaults: dict = {}  # any Campaign field (crop_mode, whisper_model, captions, ...)

    @classmethod
    def load(cls, path: str | Path = "bot.yaml") -> "BotConfig":
        return cls(**(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}))

    def page(self, name: str) -> Page | None:
        return next((p for p in self.pages if p.name == name), None)
