"""Cut, reframe to 9:16 and burn animated captions with ffmpeg."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from statistics import median

from .config import Campaign

OUT_W, OUT_H = 1080, 1920


def probe(video: Path) -> tuple[int, int, float]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration", "-of", "json", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    st = data["streams"][0]
    return int(st["width"]), int(st["height"]), float(data["format"]["duration"])


def face_center_x(video: Path, start: float, end: float, samples: int = 12) -> float | None:
    """Median horizontal center of the largest face across sampled frames (0..1), or None."""
    try:
        import cv2
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    except (ImportError, AttributeError):  # OpenCV missing, or v5+ without Haar cascades
        print("    (face detection unavailable, using center crop)")
        return None
    cap = cv2.VideoCapture(str(video))
    centers = []
    for i in range(samples):
        t = start + (end - start) * (i + 0.5) / samples
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        scale = 640 / w
        small = cv2.resize(frame, (640, int(h * scale)))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(40, 40))
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            centers.append((x + fw / 2) / 640)
    cap.release()
    return median(centers) if len(centers) >= max(2, samples // 4) else None


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def build_ass(segments: list[dict], start: float, end: float, c: Campaign) -> str:
    """Word-by-word captions: a few words on screen, the spoken word highlighted."""
    words = [w for s in segments for w in s["words"] if w["end"] > start and w["start"] < end]
    rr, gg, bb = c.caption_highlight_color[0:2], c.caption_highlight_color[2:4], c.caption_highlight_color[4:6]
    hl = f"&H00{bb}{gg}{rr}&"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{c.caption_font},{c.caption_font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,60,60,520,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # group words into short lines; break on long pauses and sentence ends
    chunks: list[list[dict]] = []
    for w in words:
        if (not chunks or len(chunks[-1]) >= c.caption_words_per_line
                or w["start"] - chunks[-1][-1]["end"] > 0.6
                or chunks[-1][-1]["word"].endswith((".", "!", "?", "।"))):
            chunks.append([])
        chunks[-1].append(w)

    lines = []
    for ci, chunk in enumerate(chunks):
        next_start = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else end
        tokens = [_ass_escape(w["word"].upper() if c.caption_uppercase else w["word"]) for w in chunk]
        for wi, w in enumerate(chunk):
            ws = w["start"]
            we = chunk[wi + 1]["start"] if wi + 1 < len(chunk) else min(w["end"] + 0.4, next_start)
            parts = [
                f"{{\\c{hl}\\fscx112\\fscy112}}{tok}{{\\r}}" if i == wi else tok
                for i, tok in enumerate(tokens)
            ]
            lines.append(
                f"Dialogue: 0,{_ass_time(ws - start)},{_ass_time(max(we, ws + 0.05) - start)},Cap,,0,0,0,,{' '.join(parts)}"
            )
    return header + "\n".join(lines) + "\n"


def render_clip(video: Path, start: float, end: float, segments: list[dict], out_file: Path, c: Campaign) -> Path:
    src_w, src_h, _ = probe(video)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    work = out_file.parent

    target_ratio = OUT_W / OUT_H
    if c.crop_mode == "blur" and src_w / src_h > target_ratio:
        graph = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},boxblur=25:2[bgb];"
            f"[fg]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
        )
    else:
        if src_w / src_h > target_ratio:  # wider than 9:16 -> crop width
            cw, ch = int(src_h * target_ratio) // 2 * 2, src_h // 2 * 2
            cx = face_center_x(video, start, end) if c.crop_mode == "face" else None
            cx = 0.5 if cx is None else cx
            x = int(min(max(cx * src_w - cw / 2, 0), src_w - cw))
            y = 0
        else:  # taller/narrower -> crop height
            cw, ch = src_w // 2 * 2, int(src_w / target_ratio) // 2 * 2
            x, y = 0, (src_h - ch) // 2
        graph = f"[0:v]crop={cw}:{ch}:{x}:{y},scale={OUT_W}:{OUT_H},setsar=1[v]"

    out_label = "[v]"
    if c.captions:
        ass_file = work / f"{out_file.stem}.ass"
        ass_file.write_text(build_ass(segments, start, end, c), encoding="utf-8")
        # relative filename + cwd avoids ffmpeg filter path-escaping issues (Windows drive colons)
        graph += f";[v]ass={ass_file.name}[vout]"
        out_label = "[vout]"

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-stats",
        "-ss", f"{start:.2f}", "-t", f"{end - start:.2f}", "-i", str(video),
        "-filter_complex", graph, "-map", out_label, "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        out_file.name,
    ]
    subprocess.run(cmd, check=True, cwd=work)
    return out_file
