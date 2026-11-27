"""Ask Claude to pick the most clip-worthy moments from a transcript."""
from __future__ import annotations

import anthropic
from pydantic import BaseModel

from .config import Campaign


class ClipIdea(BaseModel):
    start: float
    end: float
    title: str
    description: str
    hashtags: list[str]
    hook: str
    virality_score: int
    reason: str


class ClipPlan(BaseModel):
    clips: list[ClipIdea]


SYSTEM_PROMPT = """You are a senior short-form video editor who cuts long videos into \
YouTube Shorts, Instagram Reels and TikToks that get paid per view on clipping campaigns.

Pick moments that work on their own for a viewer who never saw the original video:
- The first 1-3 seconds must hook (a bold claim, a question, a surprise, conflict, a funny line).
- The clip must have a payoff or a complete thought; never stop mid-sentence or mid-joke.
- Start and end on sentence boundaries, using the timestamps given in the transcript.
- Prefer emotion, controversy, insight, humour, big numbers, and story moments over filler, \
intros, sponsor reads and housekeeping.
- Clips must not overlap.

Campaign rules from the brand override everything above when they conflict."""


def format_transcript(segments: list[dict]) -> str:
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)


def pick_clips(segments: list[dict], video_title: str, campaign: Campaign) -> list[ClipIdea]:
    client = anthropic.Anthropic()

    user = f"""Video title: {video_title or "(unknown)"}

Campaign: {campaign.campaign_name}
Campaign rules:
{campaign.rules.strip() or "(none)"}

Find the best {campaign.clips_per_video} clips. Each clip must be between \
{campaign.min_seconds} and {campaign.max_seconds} seconds long.
Write title, description and hashtags in {campaign.language}. Titles: under 70 characters, \
curiosity-driven, no clickbait lies. virality_score: 1-10. hook: the opening line viewers hear. \
reason: one sentence on why this moment works.
Return clips sorted from best to worst.

Transcript (seconds):
{format_transcript(segments)}"""

    response = client.beta.messages.parse(
        model=campaign.model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": campaign.effort},
        # On a safety decline, the API retries the same request on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": user}],
        output_format=ClipPlan,
    )

    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        raise RuntimeError(f"Claude declined this video: {getattr(details, 'explanation', '')}")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise RuntimeError(f"Claude response incomplete (stop_reason={response.stop_reason})")

    u = response.usage
    print(f"  Claude tokens: {u.input_tokens} in / {u.output_tokens} out")
    return response.parsed_output.clips


def snap_to_speech(idea: ClipIdea, segments: list[dict], campaign: Campaign, duration: float) -> tuple[float, float] | None:
    """Align a clip to word boundaries, enforce length limits, add small padding."""
    words = [w for s in segments for w in s["words"]]
    if not words:
        start, end = idea.start, idea.end
    else:
        # first word starting at/after the requested start (with tolerance)
        start_word = next((w for w in words if w["start"] >= idea.start - 0.5), words[-1])
        start = start_word["start"]
        # last word ending at/before the requested end (with tolerance)
        in_range = [w for w in words if w["start"] >= start and w["end"] <= idea.end + 0.5]
        end = in_range[-1]["end"] if in_range else idea.end

        if end - start > campaign.max_seconds:
            limit = start + campaign.max_seconds
            fitting = [w for w in in_range if w["end"] <= limit]
            # prefer cutting after a sentence end
            sentence_ends = [w for w in fitting if w["word"].endswith((".", "!", "?", "।"))]
            pick = sentence_ends[-1] if sentence_ends and sentence_ends[-1]["end"] - start >= campaign.min_seconds else (fitting[-1] if fitting else None)
            end = pick["end"] if pick else limit

    start = max(0.0, start - 0.15)
    end = min(duration, end + 0.4)
    if end - start < max(5, campaign.min_seconds * 0.6):
        return None
    return round(start, 2), round(end, 2)


def remove_overlaps(windows: list[tuple[float, float, ClipIdea]]) -> list[tuple[float, float, ClipIdea]]:
    kept: list[tuple[float, float, ClipIdea]] = []
    for s, e, idea in windows:  # already best-first
        if all(e <= ks or s >= ke for ks, ke, _ in kept):
            kept.append((s, e, idea))
    return kept
