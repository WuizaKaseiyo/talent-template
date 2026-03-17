"""Data models for AV novel production pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Chapter(BaseModel):
    """Single chapter in an episode script."""

    chapter_id: int
    narration_text: str = Field(..., min_length=1)
    image_prompts: list[str] = Field(..., min_length=1)


class EpisodeScript(BaseModel):
    """Complete episode script produced by the Writer."""

    title: str = Field(..., min_length=1)
    genre: str = Field(..., min_length=1)
    style_reference: str = Field(..., min_length=1)
    chapters: list[Chapter] = Field(..., min_length=1, max_length=8)
