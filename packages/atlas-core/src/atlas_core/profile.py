"""The profile: single source of truth for what the user can honestly claim."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from atlas_core.contracts import SCHEMA_VERSION, SchemaVersion

Status = Literal["strong", "partial", "gap"]


class Evidence(BaseModel):
    text: str
    source: str


class SkillEntry(BaseModel):
    id: str
    name: str
    status: Status
    evidence: list[Evidence] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)


class Axis(BaseModel):
    id: str
    name: str
    keywords: list[str] = Field(default_factory=list)


class Profile(BaseModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    skills: list[SkillEntry]
    aliases: dict[str, str] = Field(default_factory=dict)
    axes: list[Axis] = Field(default_factory=list)

    def resolve(self, name: str) -> str:
        lowered = {alias.lower(): target for alias, target in self.aliases.items()}
        return lowered.get(name.lower(), name)

    def skill_ids(self) -> set[str]:
        return {skill.id for skill in self.skills}


def load_profile(path: Path) -> Profile:
    with path.open(encoding="utf-8") as handle:
        return Profile.model_validate(yaml.safe_load(handle))
