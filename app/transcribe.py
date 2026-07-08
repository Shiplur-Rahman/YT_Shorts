"""Audio extraction (ffmpeg) and transcription (faster-whisper)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from faster_whisper import WhisperModel

from app.schemas import Segment, Transcript, Word

WHISPER_MODEL_SIZE = "small"

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def extract_audio(video_path: Path, wav_path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", str(wav_path)],
        check=True,
        capture_output=True,
    )


def transcribe(wav_path: Path, on_progress=None) -> Transcript:
    """Transcribe with word-level timestamps. on_progress(seconds_done, total_seconds)."""
    model = _get_model()
    segments_iter, info = model.transcribe(str(wav_path), word_timestamps=True, vad_filter=True)

    segments: list[Segment] = []
    for seg in segments_iter:
        words = [Word(start=w.start, end=w.end, text=w.word.strip()) for w in (seg.words or [])]
        segments.append(Segment(start=seg.start, end=seg.end, text=seg.text.strip(), words=words))
        if on_progress:
            on_progress(seg.end, info.duration)

    return Transcript(language=info.language, duration=info.duration, segments=segments)


def transcribe_video(video_path: Path, job_dir: Path, on_progress=None) -> Transcript:
    wav_path = job_dir / "audio.wav"
    extract_audio(video_path, wav_path)
    transcript = transcribe(wav_path, on_progress)
    (job_dir / "transcript.json").write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    return transcript


if __name__ == "__main__":
    import sys

    video = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else video.parent
    t = transcribe_video(video, out_dir, on_progress=lambda d, tot: print(f"\r{d:.0f}/{tot:.0f}s", end=""))
    print(f"\n{len(t.segments)} segments, language={t.language}")
