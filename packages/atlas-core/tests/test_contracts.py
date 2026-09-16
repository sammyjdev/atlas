import json
from datetime import date

import pytest
from atlas_core import contracts
from pydantic import ValidationError


def test_demand_signal_round_trips_with_schema_version():
    signal = contracts.DemandSignal(
        id="sig-1",
        window_start=date(2026, 9, 1),
        window_end=date(2026, 9, 15),
        postings=42,
        skills=[contracts.SkillDemand(name="langgraph", count=21, share=0.5)],
    )
    data = json.loads(signal.model_dump_json())
    assert data["schema_version"] == "1"
    assert contracts.DemandSignal.model_validate(data) == signal


def test_skill_share_is_a_fraction():
    with pytest.raises(ValidationError):
        contracts.SkillDemand(name="rag", count=3, share=1.5)


def test_research_item_scores_are_unit_interval():
    with pytest.raises(ValidationError):
        contracts.ItemScores(relevance=2.0, quality=0.5, novelty=0.5, recency=0.5, social=0.5)


def test_job_posting_defaults():
    posting = contracts.JobPosting(
        id="p-1", source="alert", title="AI Engineer", company="Acme", text="Build RAG."
    )
    assert posting.url is None and posting.posted_at is None and posting.demands == []


def test_unknown_schema_version_is_rejected():
    with pytest.raises(ValidationError):
        contracts.StudyRequest(
            schema_version="2", id="s-1", topic="MMR", axis="rag", reason="gap"
        )


def test_export_json_schemas_writes_one_file_per_item(tmp_path):
    paths = contracts.export_json_schemas(tmp_path)
    names = sorted(p.name for p in paths)
    assert names == [
        "DemandSignal.schema.json",
        "JobPosting.schema.json",
        "ResearchItem.schema.json",
        "StudyRequest.schema.json",
    ]
    schema = json.loads((tmp_path / "DemandSignal.schema.json").read_text())
    assert schema["properties"]["schema_version"]["const"] == "1"
