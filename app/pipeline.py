"""Runs the full upload -> shorts pipeline for one job, reporting progress."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.captions import build_ass_for_clip
from app.crop import compute_crop
from app.render import render_clip
from app.schemas import ClipResult, JobMetadata
from app.select_clips import select_clips
from app.transcribe import transcribe_video

ProgressFn = Callable[[str, float], None]  # (stage, 0..1 progress within stage)


def run_pipeline(
    job_id: str,
    video_path: Path,
    job_dir: Path,
    progress: ProgressFn,
    captions: bool = False,
) -> JobMetadata:
    clips_dir = job_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    progress("transcribing", 0.0)
    transcript = transcribe_video(
        video_path, job_dir,
        on_progress=lambda done, total: progress("transcribing", done / max(total, 1)),
    )

    progress("selecting", 0.0)
    picks = select_clips(transcript)
    if not picks:
        raise RuntimeError("No suitable clip moments were found in this video")

    results: list[ClipResult] = []
    for i, pick in enumerate(picks):
        progress("rendering", i / len(picks))
        crop = compute_crop(video_path, pick.start_s, pick.end_s)
        filename = f"clip_{i + 1:02d}.mp4"
        subtitle_path = None
        if captions:
            ass_path = clips_dir / f"clip_{i + 1:02d}.ass"
            if build_ass_for_clip(transcript, pick.start_s, pick.end_s, ass_path):
                subtitle_path = ass_path
        render_clip(
            video_path, clips_dir / filename, pick.start_s, pick.end_s, crop,
            subtitle_path=subtitle_path,
        )
        results.append(
            ClipResult(
                index=i + 1,
                filename=filename,
                start_s=pick.start_s,
                end_s=pick.end_s,
                duration_s=round(pick.end_s - pick.start_s, 2),
                hook_score=pick.hook_score,
                title=pick.title,
                description=pick.description,
                hashtags=pick.hashtags,
                reason=pick.reason,
            )
        )

    metadata = JobMetadata(job_id=job_id, source_filename=video_path.name, clips=results)
    (job_dir / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    progress("done", 1.0)
    return metadata
