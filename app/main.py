"""FastAPI server: upload endpoint, background job runner, clip serving, static UI."""
from __future__ import annotations

import io
import json
import os
import threading
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.pipeline import run_pipeline

ROOT = Path(__file__).resolve().parent.parent
UPLOADS_DIR = ROOT / "data" / "uploads"
JOBS_DIR = ROOT / "data" / "jobs"
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

load_dotenv(ROOT / ".env")

app = FastAPI(title="YT Shorts Generator")


@dataclass
class Job:
    id: str
    source_filename: str
    status: str = "queued"  # queued | running | done | error
    stage: str = "queued"
    progress: float = 0.0
    error: str | None = None
    metadata: dict | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


jobs: dict[str, Job] = {}


def _run_job(job: Job, video_path: Path, job_dir: Path, captions: bool) -> None:
    def progress(stage: str, frac: float) -> None:
        with job.lock:
            job.stage = stage
            job.progress = round(min(max(frac, 0.0), 1.0), 3)

    try:
        with job.lock:
            job.status = "running"
        metadata = run_pipeline(job.id, video_path, job_dir, progress, captions=captions)
        with job.lock:
            job.status = "done"
            job.stage = "done"
            job.progress = 1.0
            job.metadata = metadata.model_dump()
    except Exception as exc:  # surface any pipeline failure to the UI
        with job.lock:
            job.status = "error"
            job.error = str(exc)


@app.post("/api/upload")
async def upload(file: UploadFile, captions: bool = Form(False)):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(500, "ANTHROPIC_API_KEY is not set. Add it to the .env file and restart.")
    ext = Path(file.filename or "video.mp4").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{ext}'")

    job_id = uuid.uuid4().hex[:12]
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    video_path = UPLOADS_DIR / f"{job_id}{ext}"
    with video_path.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    job = Job(id=job_id, source_filename=file.filename or video_path.name)
    jobs[job_id] = job
    threading.Thread(target=_run_job, args=(job, video_path, job_dir, captions), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = _get_job(job_id)
    with job.lock:
        return {
            "job_id": job.id,
            "source_filename": job.source_filename,
            "status": job.status,
            "stage": job.stage,
            "progress": job.progress,
            "error": job.error,
            "metadata": job.metadata,
        }


@app.get("/api/jobs/{job_id}/clips/{filename}")
def get_clip(job_id: str, filename: str):
    _get_job(job_id)
    if Path(filename).name != filename or not filename.endswith(".mp4"):
        raise HTTPException(400, "Invalid clip filename")
    clip_path = JOBS_DIR / job_id / "clips" / filename
    if not clip_path.is_file():
        raise HTTPException(404, "Clip not found")
    return FileResponse(clip_path, media_type="video/mp4", filename=filename)


@app.get("/api/jobs/{job_id}/download-all")
def download_all(job_id: str):
    job = _get_job(job_id)
    clips_dir = JOBS_DIR / job_id / "clips"
    metadata_path = JOBS_DIR / job_id / "metadata.json"
    if job.status != "done" or not clips_dir.is_dir():
        raise HTTPException(400, "Job is not finished")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for clip in sorted(clips_dir.glob("*.mp4")):
            zf.write(clip, clip.name)
        if metadata_path.is_file():
            zf.write(metadata_path, "metadata.json")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="shorts_{job_id}.zip"'},
    )


def _get_job(job_id: str) -> Job:
    job = jobs.get(job_id)
    if job is None:
        # Recover finished jobs from disk after a server restart.
        metadata_path = JOBS_DIR / job_id / "metadata.json"
        if metadata_path.is_file():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            job = Job(
                id=job_id,
                source_filename=metadata.get("source_filename", ""),
                status="done",
                stage="done",
                progress=1.0,
                metadata=metadata,
            )
            jobs[job_id] = job
        else:
            raise HTTPException(404, "Job not found")
    return job


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
