"""Pydantic models: profile entries, extracted demands, and match verdicts."""
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["strong", "partial", "gap"]


class Demand(BaseModel):
    name: str
    kind: Literal["core", "nice-to-have"]
    quote: str


class Demands(BaseModel):
    demands: list[Demand]


class Verdict(BaseModel):
    demand: str
    verdict: Status
    evidence: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    justification: str
    resolved_by: Literal["alias", "llm"]


class ResidueVerdicts(BaseModel):
    verdicts: list[Verdict]
