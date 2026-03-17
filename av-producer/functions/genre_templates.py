"""Genre template loader for AV novel production."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class GenreTemplate:
    """A genre template defining story structure and style."""

    id: str
    name: str
    description: str
    tone: str
    image_style: str
    chapter_count_min: int = 5
    chapter_count_max: int = 7
    pacing: str = "medium"
    story_beats: list[str] = field(default_factory=list)
    example_themes: list[str] = field(default_factory=list)


def load_genre_template(genre_id: str, templates_dir: Path) -> GenreTemplate:
    """Load a genre template by ID from the templates directory."""
    path = templates_dir / f"{genre_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Genre template not found: {path}")
    data = yaml.safe_load(path.read_text())
    return GenreTemplate(**data)


def list_genre_templates(templates_dir: Path) -> list[str]:
    """List available genre template IDs."""
    if not templates_dir.exists():
        return []
    return sorted(p.stem for p in templates_dir.glob("*.yaml"))
