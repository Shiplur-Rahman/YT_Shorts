"""Pydantic models shared across the pipeline."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Word(BaseModel):
    start: float
    end: float
    text: str


class Segment(BaseModel):
    start: float
    end: float
    text: str
    words: list[Word] = []


class Transcript(BaseModel):
    language: str
    duration: float
    segments: list[Segment]

    def all_words(self) -> list[Word]:
        return [w for seg in self.segments for w in seg.words]


class ClipPick(BaseModel):
    """One clip suggestion returned by Claude."""

    start_s: float = Field(description="Clip start time in seconds, from the transcript timestamps")
    end_s: float = Field(description="Clip end time in seconds; the moment must be self-contained")
    hook_score: int = Field(description="1-10: how strongly the first 2 seconds hook a scrolling viewer")
    title: str = Field(description="YouTube Shorts title, under 80 chars, curiosity-driven but not clickbait-lying")
    description: str = Field(description="1-2 sentence YouTube description")
    hashtags: list[str] = Field(description="3-5 hashtags without the # symbol, e.g. 'podcast'")
    reason: str = Field(description="One sentence: why this moment works as a Short")


class ClipSelection(BaseModel):
    clips: list[ClipPick]


class ClipResult(BaseModel):
    """A rendered clip plus its metadata, written to metadata.json."""

    index: int
    filename: str
    start_s: float
    end_s: float
    duration_s: float
    hook_score: int
    title: str
    description: str
    hashtags: list[str]
    reason: str


class JobMetadata(BaseModel):
    job_id: str
    source_filename: str
    clips: list[ClipResult]
