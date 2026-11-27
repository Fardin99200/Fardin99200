"""Campaign settings: defaults, YAML loading, CLI overrides."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml


@dataclass
class Campaign:
    campaign_name: str = "default"
    sources: list[str] = field(default_factory=list)

    # Rules copied from the Vyro campaign page (brand mentions, banned topics, etc.)
    rules: str = ""
    # Language for titles/descriptions, e.g. "English", "Hinglish", "Hindi"
    language: str = "English"

    clips_per_video: int = 5
    min_seconds: int = 20
    max_seconds: int = 60

    # Rendering
    crop_mode: str = "face"  # face | center | blur
    captions: bool = True
    caption_words_per_line: int = 3
    caption_font: str = "Arial"
    caption_font_size: int = 86
    caption_highlight_color: str = "FFFF00"  # RRGGBB for the word being spoken
    caption_uppercase: bool = True

    # Extra effects
    hook_text: bool = True        # the clip's title as a bold box at the top
    hook_seconds: float = 0       # 0 = whole clip, else only the first N seconds
    progress_bar: bool = True     # thin bar at the bottom that fills up
    zoom: bool = True             # slow push-in (keeps the frame moving)
    music_dir: str = "music"      # put royalty-free .mp3 files here; empty folder = no music
    music_volume: float = 0.12    # 0.05 quiet ... 0.3 loud

    # Transcription (faster-whisper model: tiny, base, small, medium, large-v3)
    whisper_model: str = "small"
    whisper_language: str | None = None  # None = auto-detect

    # Upload
    upload: bool = False
    privacy: str = "private"  # private | unlisted | public
    required_hashtags: list[str] = field(default_factory=lambda: ["#shorts"])
    description_suffix: str = ""

    # Claude
    model: str = "claude-opus-5-5"
    effort: str = "high"

    output_dir: str = "output"
    download_dir: str = "downloads"

    @classmethod
    def load(cls, path: str | Path | None) -> "Campaign":
        if not path:
            return cls()
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown keys in {path}: {', '.join(sorted(unknown))}")
        return cls(**data)
