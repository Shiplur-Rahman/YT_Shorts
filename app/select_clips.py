"""Pick the best Short-worthy moments from a transcript using the Claude API."""
from __future__ import annotations

import anthropic

from app.schemas import ClipPick, ClipSelection, Transcript

MODEL = "claude-opus-4-8"
MIN_CLIP_S = 15.0
MAX_CLIP_S = 60.0
PAD_START_S = 0.3
PAD_END_S = 0.5

SYSTEM_PROMPT = """You are an expert YouTube Shorts editor specializing in podcast and \
talking-head clips. You know the current format that performs: a moment that hooks in the \
first two seconds (a bold claim, a surprising fact, a question, an emotional beat), stays \
self-contained without needing outside context, and ends on a satisfying or punchy note.

You will receive a transcript with second-based timestamps. Pick the strongest moments to \
cut into Shorts. Rules:
- Each clip must be 20-55 seconds long and start/end at natural sentence boundaries.
- The opening line must work as a hook for a viewer who is scrolling and has zero context.
- Never start mid-thought or on a filler word; never cut off the ending.
- Clips must not overlap.
- Prefer fewer great clips over many mediocre ones.
- Titles: curiosity-driven, honest, under 80 characters, no ALL CAPS spam."""


def build_prompt(transcript: Transcript, max_clips: int) -> str:
    lines = [f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}" for seg in transcript.segments]
    return (
        f"Here is the transcript of a {transcript.duration:.0f}-second video. "
        f"Pick up to {max_clips} of the strongest Shorts moments.\n\n" + "\n".join(lines)
    )


def select_clips(transcript: Transcript, max_clips: int = 6) -> list[ClipPick]:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_prompt(transcript, max_clips)}],
        output_format=ClipSelection,
    )
    selection = response.parsed_output
    if selection is None:
        raise RuntimeError("Claude returned no parseable clip selection")
    clips = [_snap_to_words(c, transcript) for c in selection.clips]
    clips = [c for c in clips if MIN_CLIP_S <= (c.end_s - c.start_s) <= MAX_CLIP_S]
    clips.sort(key=lambda c: c.hook_score, reverse=True)
    return clips


def _snap_to_words(clip: ClipPick, transcript: Transcript) -> ClipPick:
    """Snap start/end to the nearest word boundaries, then pad slightly."""
    words = transcript.all_words()
    if words:
        start = min((w.start for w in words), key=lambda s: abs(s - clip.start_s))
        end = min((w.end for w in words), key=lambda e: abs(e - clip.end_s))
    else:
        start, end = clip.start_s, clip.end_s
    start = max(0.0, start - PAD_START_S)
    end = min(transcript.duration, end + PAD_END_S)
    return clip.model_copy(update={"start_s": round(start, 2), "end_s": round(end, 2)})


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    transcript = Transcript.model_validate_json(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for c in select_clips(transcript):
        print(f"{c.start_s:>7.1f}-{c.end_s:<7.1f} score={c.hook_score} {c.title}")
