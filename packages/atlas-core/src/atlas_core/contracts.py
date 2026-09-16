"""Exchange item contracts shared by MERIT, ORBIT and SAGE.

Every item carries schema_version so a consumer can refuse what it does not
understand. Bump SCHEMA_VERSION only on a breaking field change.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

SchemaVersion = Literal["1"]
SCHEMA_VERSION: SchemaVersion = "1"
_Version = SchemaVersion
_Unit = Field(ge=0.0, le=1.0)


class Demand(BaseModel):
    name: str
    kind: Literal["core", "nice-to-have"]
    quote: str


class JobPosting(BaseModel):
    schema_version: _Version = SCHEMA_VERSION
    id: str
    source: Literal["inmail", "alert", "manual"]
    title: str
    company: str
    url: str | None = None
    posted_at: date | None = None
    text: str
    demands: list[Demand] = Field(default_factory=list)


class SkillDemand(BaseModel):
    name: str
    count: int = Field(ge=0)
    share: float = _Unit


class DemandSignal(BaseModel):
    schema_version: _Version = SCHEMA_VERSION
    id: str
    window_start: date
    window_end: date
    postings: int = Field(ge=0)
    skills: list[SkillDemand]


class ItemScores(BaseModel):
    relevance: float = _Unit
    quality: float = _Unit
    novelty: float = _Unit
    recency: float = _Unit
    social: float = _Unit


class ResearchItem(BaseModel):
    schema_version: _Version = SCHEMA_VERSION
    id: str
    kind: Literal["paper", "post", "thesis", "news"]
    title: str
    url: str
    canonical_key: str
    published_at: date | None = None
    axis: str
    scores: ItemScores
    rank: int = Field(ge=1)
    summary: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class StudyRequest(BaseModel):
    """Reserved: SAGE asks ORBIT for material on a gap. Not produced in v1."""

    schema_version: _Version = SCHEMA_VERSION
    id: str
    topic: str
    axis: str
    reason: str


EXCHANGE_ITEMS: tuple[type[BaseModel], ...] = (
    JobPosting,
    DemandSignal,
    ResearchItem,
    StudyRequest,
)


def export_json_schemas(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for model in EXCHANGE_ITEMS:
        path = out_dir / f"{model.__name__}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2) + "\n")
        written.append(path)
    return written
