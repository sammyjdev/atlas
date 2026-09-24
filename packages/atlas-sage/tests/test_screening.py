"""The screening track: same machinery, a rubric that grades something else."""

from pathlib import Path

from atlas_sage import pipeline
from atlas_sage.state import State
from atlas_sage.track import SCREENING, TECHNICAL

VALID = """---
vaga: "Acme - Senior AI Engineer"
cards:
  - q: "Where are you based, and are you currently employed?"
    a: |
      - States a city and timezone, not just a country
      - Says whether they are working now and what notice they owe
      - A weak answer gives the country only and leaves the timezone open
  - q: "Of everything you have built, which ONE are you proudest of?"
    a: |
      - Commits to a single project instead of listing several
      - Says what they personally did in it, not what the team shipped
      - A weak answer names three projects and ranks none
---

## Summary

This posting screens for someone who can own a delivery end to end.

## Interview Q&A

**Q: Where are you based, and are you currently employed?**
A: A city and a timezone, plus the notice period.

**Q: Which ONE are you proudest of?**
A: One project, their own contribution named.
"""

CRITIC_OK = '{"approved": true, "confidence": "high", "issues": []}'


def _run(monkeypatch, tmp_path: Path, track, writer_out=VALID, critic_out=CRITIC_OK):
    monkeypatch.setattr(pipeline, "writer_call", lambda system, user: writer_out)
    monkeypatch.setattr(pipeline, "critic_call", lambda system, user: critic_out)
    state = State()
    result = pipeline.run_interview(
        state=state,
        profile="Java-first, no fine-tuning experience.",
        jd="Senior AI Engineer at Acme. LoRA required.",
        jd_slug="acme-senior-ai-engineer",
        vault_root=tmp_path,
        today="2026-09-13",
        track=track,
    )
    return state, result


def test_screening_writes_under_its_own_key_so_both_tracks_can_run(
    tmp_path, monkeypatch
):
    """One posting yields two interviews, not one that overwrites the other.

    The technical call and the screening call are different conversations about
    the same job. Sharing a state key would let whichever ran first block the
    other for good.
    """
    state, result = _run(monkeypatch, tmp_path, SCREENING)

    assert result["status"] == "approved"
    assert result["slug"] == "screening:acme-senior-ai-engineer"
    assert "screening:acme-senior-ai-engineer" in state.done
    assert "interview:acme-senior-ai-engineer" not in state.done


def test_screening_lands_in_its_own_nicho_not_beside_the_technical_ones(
    tmp_path, monkeypatch
):
    """A separate directory, not a filename suffix.

    Three consumers glob the interview directory and skip only "-qa.md" and
    "-voice.md": the Anki export, the label sheet, and the recitability
    measurement. A screening file sitting in that directory would be swept into
    all three - into the sheet a recruiter labels for TECHNICAL question
    quality, and into the published recitability baseline, where HR questions
    would be scored by a rule written for technical form.

    anki.export skips a nicho with no deck id, so the directory alone is the
    whole fix.
    """
    _run(monkeypatch, tmp_path, TECHNICAL)
    _run(monkeypatch, tmp_path, SCREENING)

    technical = {p.name for p in (tmp_path / "interview").glob("*.md")}
    screening = {p.name for p in (tmp_path / "screening").glob("*.md")}

    assert technical == {
        "acme-senior-ai-engineer.md",
        "acme-senior-ai-engineer-qa.md",
        "acme-senior-ai-engineer-voice.md",
    }
    assert screening == {
        "acme-senior-ai-engineer.md",
        "acme-senior-ai-engineer-qa.md",
        "acme-senior-ai-engineer-voice.md",
    }

    from atlas_sage.anki import NICHO_DECK_IDS

    assert "screening" not in NICHO_DECK_IDS, "screening cards must not reach Anki"


def test_screening_uses_the_screening_prompts_not_the_technical_ones(
    tmp_path, monkeypatch
):
    """The rubric is the whole difference between the tracks.

    A screening question has no number and no consequence, so running it past
    the technical critic would reject every single one.
    """
    seen = {}

    def fake_writer(system, user):
        seen["writer_system"] = system
        return VALID

    def fake_critic(system, user):
        seen["critic_system"] = system
        return CRITIC_OK

    monkeypatch.setattr(pipeline, "writer_call", fake_writer)
    monkeypatch.setattr(pipeline, "critic_call", fake_critic)
    pipeline.run_interview(
        state=State(),
        profile="p",
        jd="j",
        jd_slug="s",
        vault_root=tmp_path,
        today="2026-09-13",
        track=SCREENING,
    )

    assert "recruiter" in seen["writer_system"].lower()
    assert "bluffer" not in seen["critic_system"].lower()
    assert "recruiter" in seen["critic_system"].lower()


def test_technical_track_is_still_the_default(tmp_path, monkeypatch):
    """Callers that never heard of tracks keep the behaviour they had."""
    monkeypatch.setattr(pipeline, "writer_call", lambda system, user: VALID)
    monkeypatch.setattr(pipeline, "critic_call", lambda system, user: CRITIC_OK)
    state = State()
    result = pipeline.run_interview(
        state=state,
        profile="p",
        jd="j",
        jd_slug="acme",
        vault_root=tmp_path,
        today="2026-09-13",
    )
    assert result["slug"] == "interview:acme"
