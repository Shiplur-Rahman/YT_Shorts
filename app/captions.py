"""Generate ASS subtitle files for burned-in captions from word-level timestamps."""
from __future__ import annotations

from pathlib import Path

from app.schemas import Transcript, Word

MAX_WORDS_PER_GROUP = 3
MAX_GAP_S = 0.6  # start a new group after a pause longer than this
MIN_HOLD_S = 0.8  # keep very short groups on screen at least this long

# 1080x1920 canvas, big bold white text with a thick black outline,
# centered horizontally and sitting in the lower third (above the YT UI).
ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial Black,96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,9,0,2,60,60,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Text
"""

# Quick pop-in: start slightly oversized, settle to 100% in 80ms.
POP_TAG = r"{\fscx115\fscy115\t(0,80,\fscx100\fscy100)}"


def build_ass_for_clip(transcript: Transcript, start_s: float, end_s: float, ass_path: Path) -> bool:
    """Write an ASS file covering [start_s, end_s], timestamps relative to start_s.

    Returns False (and writes nothing) if the window contains no words.
    """
    words = [w for w in transcript.all_words() if w.end > start_s and w.start < end_s]
    groups = _group_words(words)
    if not groups:
        return False

    duration = end_s - start_s
    lines = [ASS_HEADER]
    for gi, group in enumerate(groups):
        g_start = max(group[0].start - start_s, 0.0)
        g_end = max(group[-1].end - start_s, g_start + MIN_HOLD_S)
        # Never overlap the next group, never run past the clip.
        if gi + 1 < len(groups):
            g_end = min(g_end, groups[gi + 1][0].start - start_s)
        g_end = min(g_end, duration)
        if g_end <= g_start:
            continue
        text = " ".join(_clean(w.text) for w in group if _clean(w.text))
        if not text:
            continue
        lines.append(
            f"Dialogue: 0,{_ass_time(g_start)},{_ass_time(g_end)},Caption,,0,0,0,{POP_TAG}{text}\n"
        )

    ass_path.write_text("".join(lines), encoding="utf-8")
    return True


def _group_words(words: list[Word]) -> list[list[Word]]:
    """Split words into short display groups, breaking on pauses."""
    groups: list[list[Word]] = []
    current: list[Word] = []
    for w in words:
        if current and (
            len(current) >= MAX_WORDS_PER_GROUP or w.start - current[-1].end > MAX_GAP_S
        ):
            groups.append(current)
            current = []
        current.append(w)
    if current:
        groups.append(current)
    return groups


def _clean(text: str) -> str:
    # Braces would be parsed as ASS override tags; captions read best in caps.
    return text.replace("{", "").replace("}", "").strip().upper()


def _ass_time(t: float) -> str:
    cs = max(int(round(t * 100)), 0)
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
