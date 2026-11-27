"""Speech-to-text with word timestamps (faster-whisper, runs locally and free)."""
from __future__ import annotations

import json
from pathlib import Path


def transcribe(video: Path, cache_file: Path, model_size: str = "small", language: str | None = None) -> list[dict]:
    """Return segments: [{start, end, text, words: [{start, end, word}]}]. Cached as JSON."""
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    from faster_whisper import WhisperModel  # heavy import, only when needed

    try:
        model = WhisperModel(model_size, device="cuda", compute_type="float16")
        print(f"  Whisper '{model_size}' on GPU")
    except Exception:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        print(f"  Whisper '{model_size}' on CPU (slow for long videos; use a smaller model if needed)")

    segments_iter, info = model.transcribe(
        str(video), language=language, word_timestamps=True, vad_filter=True
    )
    print(f"  Detected language: {info.language} ({info.language_probability:.0%})")

    segments = []
    for seg in segments_iter:
        words = [
            {"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word.strip()}
            for w in (seg.words or [])
            if w.word.strip()
        ]
        segments.append(
            {"start": round(seg.start, 2), "end": round(seg.end, 2), "text": seg.text.strip(), "words": words}
        )
        print(f"\r  Transcribed up to {seg.end/60:.1f} min", end="", flush=True)
    print()

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(segments, ensure_ascii=False, indent=1), encoding="utf-8")
    return segments
