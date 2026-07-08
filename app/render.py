"""Cut and render a clip to a 1080x1920 vertical mp4 with ffmpeg."""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.crop import CropWindow


def render_clip(
    video_path: Path,
    out_path: Path,
    start_s: float,
    end_s: float,
    crop: CropWindow,
    subtitle_path: Path | None = None,
) -> None:
    vf = f"crop={crop.w}:{crop.h}:{crop.x}:{crop.y},scale=1080:1920"
    cwd = None
    if subtitle_path is not None:
        # Reference the .ass by bare filename and run ffmpeg from its folder:
        # absolute Windows paths (colons, backslashes) break the filter parser.
        vf += f",subtitles={subtitle_path.name}"
        cwd = str(subtitle_path.parent)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_s:.2f}",
        "-to", f"{end_s:.2f}",
        "-i", str(video_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {out_path.name}:\n{result.stderr[-2000:]}")
