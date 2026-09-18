from pathlib import Path

import pytest
from atlas_core import profile
from pydantic import ValidationError

FIXTURE = Path(__file__).parent / "fixtures" / "profile.yaml"


def test_load_profile_reads_skills_aliases_and_axes():
    loaded = profile.load_profile(FIXTURE)
    assert [s.id for s in loaded.skills] == ["langgraph", "knowledge-graphs"]
    assert loaded.skills[0].evidence[0].source == "github.com/example/merit"
    assert [a.id for a in loaded.axes] == ["agents", "kg"]


def test_resolve_uses_aliases_case_insensitively():
    loaded = profile.load_profile(FIXTURE)
    assert loaded.resolve("Lang Graph") == "langgraph"
    assert loaded.resolve("kg") == "knowledge-graphs"
    assert loaded.resolve("rust") == "rust"


def test_skill_ids_lists_every_skill_id():
    loaded = profile.load_profile(FIXTURE)
    assert loaded.skill_ids() == {"langgraph", "knowledge-graphs"}


def test_evidence_requires_a_source():
    with pytest.raises(ValidationError):
        profile.SkillEntry(
            id="x", name="X", status="strong", evidence=[{"text": "no source"}]
        )


def test_load_profile_reads_utf8_regardless_of_locale(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        'skills:\n'
        '  - id: observabilidade\n'
        '    name: "Observabilidade e métricas"\n'
        '    status: partial\n'
        '    evidence: []\n'
        '    claims: []\n',
        encoding="utf-8",
    )
    loaded = profile.load_profile(path)
    assert loaded.skills[0].name == "Observabilidade e métricas"
