from pathlib import Path

import pytest

from atlas_sage import pipeline
from atlas_sage.parser import ParseError, parse_interview_output
from atlas_sage.state import MAX_RETRIES, State

VALID = """---
vaga: "Acme - Senior AI Engineer"
cards:
  - q: "Your RAG returns a stale answer. Retrieval or prompt? How do you tell in under 5 minutes?"
    a: |
      - Names retrieval as the first suspect and says why
      - Gives a concrete check that separates the two layers
      - States a number: latency, chunk count or similarity threshold
      - Says what they would have instrumented beforehand
---

## Summary

The posting asks for LoRA fine-tuning, which the profile marks as a gap.

## Interview Q&A

**Q: Your RAG returns a stale answer. Retrieval or prompt?**
A: A good answer names retrieval first, gives a check that separates the layers,
and carries at least one number.
"""


def test_parses_a_valid_interview_document():
    parsed = parse_interview_output(VALID)
    assert parsed["vaga"] == "Acme - Senior AI Engineer"
    assert len(parsed["cards"]) == 1
    assert parsed["summary"].startswith("The posting asks")
    assert "retrieval" in parsed["qa"].lower()


def test_does_not_require_citations():
    """The adversarial mode has no web sources, so [^n] must not be mandatory."""
    assert "[^1]" not in VALID
    parse_interview_output(VALID)  # must not raise


def test_rejects_a_card_whose_rubric_is_too_thin():
    thin = VALID.replace(
        """      - Names retrieval as the first suspect and says why
      - Gives a concrete check that separates the two layers
      - States a number: latency, chunk count or similarity threshold
      - Says what they would have instrumented beforehand""",
        """      - Names retrieval first
      - Gives a check""",
    )
    with pytest.raises(ParseError, match="rubric"):
        parse_interview_output(thin)


def test_rejects_a_document_with_no_cards():
    empty = VALID.replace(
        """cards:
  - q: "Your RAG returns a stale answer. Retrieval or prompt? How do you tell in under 5 minutes?"
    a: |
      - Names retrieval as the first suspect and says why
      - Gives a concrete check that separates the two layers
      - States a number: latency, chunk count or similarity threshold
      - Says what they would have instrumented beforehand""",
        "cards: []",
    )
    with pytest.raises(ParseError, match="cards"):
        parse_interview_output(empty)


def test_rejects_missing_sections():
    with pytest.raises(ParseError, match="sections"):
        parse_interview_output('---\nvaga: "x"\ncards: []\n---\n\nno sections here\n')


CRITIC_OK = '{"approved": true, "confidence": "high", "issues": []}'
CRITIC_TOO_EASY = (
    '{"approved": false, "confidence": "high", "issues": ['
    '{"location": "Q&A #1", "problem": "recitable", "severity": "major"}]}'
)

PROFILE = "Strong: RAG, Python. Gap: LoRA fine-tuning, PyTorch."
JD = "# Senior AI Engineer - Acme\nWe need LoRA fine-tuning and RAG in production."


def test_run_interview_writes_vault_and_records_state(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(pipeline, "writer_call", lambda s, u: VALID)
    monkeypatch.setattr(pipeline, "critic_call", lambda s, u: CRITIC_OK)
    state = State()

    result = pipeline.run_interview(
        state=state,
        profile=PROFILE,
        jd=JD,
        jd_slug="acme-senior-ai-engineer",
        vault_root=tmp_path,
        today="2026-09-12",
    )

    assert result["status"] == "approved"
    assert (tmp_path / "interview" / "acme-senior-ai-engineer.md").exists()
    assert "interview:acme-senior-ai-engineer" in state.done


def test_run_interview_retries_when_questions_are_too_easy(tmp_path: Path, monkeypatch):
    """The inverted critic rejects weak questions; the writer gets one revision."""
    calls = {"writer": 0}

    def writer(_s, _u):
        calls["writer"] += 1
        return VALID

    monkeypatch.setattr(pipeline, "writer_call", writer)
    monkeypatch.setattr(pipeline, "critic_call", lambda s, u: CRITIC_TOO_EASY)
    state = State()

    result = pipeline.run_interview(
        state=state,
        profile=PROFILE,
        jd=JD,
        jd_slug="acme-senior-ai-engineer",
        vault_root=tmp_path,
        today="2026-09-12",
    )

    assert result["status"] == "rejected"
    assert calls["writer"] == 2  # original + one revision
    assert not (tmp_path / "interview").exists()
    assert state.retries.get("interview:acme-senior-ai-engineer") == 1


def test_run_interview_gives_up_after_max_retries(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(pipeline, "writer_call", lambda s, u: VALID)
    monkeypatch.setattr(pipeline, "critic_call", lambda s, u: CRITIC_TOO_EASY)
    slug = "interview:acme-senior-ai-engineer"
    state = State(retries={slug: MAX_RETRIES - 1})

    pipeline.run_interview(
        state=state,
        profile=PROFILE,
        jd=JD,
        jd_slug="acme-senior-ai-engineer",
        vault_root=tmp_path,
        today="2026-09-12",
    )

    assert f"__failed__:{slug}" in state.done


def test_run_interview_skips_a_posting_already_done(tmp_path: Path, monkeypatch):
    def boom(_s, _u):
        raise AssertionError("must not call the model for an already-done posting")

    monkeypatch.setattr(pipeline, "writer_call", boom)
    state = State(done=["interview:acme-senior-ai-engineer"])

    result = pipeline.run_interview(
        state=state,
        profile=PROFILE,
        jd=JD,
        jd_slug="acme-senior-ai-engineer",
        vault_root=tmp_path,
        today="2026-09-12",
    )

    assert result["status"] == "skipped"


def test_interview_cards_reach_the_anki_deck(tmp_path: Path, monkeypatch):
    """anki.export silently skips vault dirs with no deck id - guard that."""
    from atlas_sage.anki import export

    monkeypatch.setattr(pipeline, "writer_call", lambda s, u: VALID)
    monkeypatch.setattr(pipeline, "critic_call", lambda s, u: CRITIC_OK)
    pipeline.run_interview(
        state=State(),
        profile=PROFILE,
        jd=JD,
        jd_slug="acme-senior-ai-engineer",
        vault_root=tmp_path,
        today="2026-09-12",
    )

    counts = export(tmp_path, tmp_path / "out.apkg")

    assert counts.get("interview") == 1, f"interview cards were dropped: {counts}"
    assert (tmp_path / "out.apkg").exists()


def test_critic_prompt_caps_the_issue_list():
    """The critic must fit its model's 1000-token OTPM ceiling.

    An uncapped issue list truncated the JSON mid-string on a real run, which
    surfaces as a parse error rather than as a rate-limit error - much harder to
    diagnose. The cap lives in the prompt, not in max_tokens.
    """
    from atlas_sage.prompts import INTERVIEW_CRITIC_USER_TEMPLATE

    assert "AT MOST 5 issues" in INTERVIEW_CRITIC_USER_TEMPLATE


def test_voice_prompt_is_a_ready_to_paste_interview_script(tmp_path):
    """The voice layer is template-only: no model call, no extra cost."""
    from atlas_sage.vault import write_voice_prompt

    parsed = {
        "vaga": "Acme - Senior AI Engineer",
        "cards": [
            {
                "q": "Why 0.50 and not 0.85?",
                "a": "- names cosine profiling\n- gives a number\n- says what breaks",
            },
            {
                "q": "What pages you at 3AM?",
                "a": "- names a failure mode\n- has a metric\n- says the fallback",
            },
        ],
    }
    path = write_voice_prompt(
        root=tmp_path,
        nicho="interview",
        slug="acme",
        title="Acme - Senior AI Engineer",
        created="2026-09-12",
        parsed=parsed,
    )
    text = path.read_text()

    assert path.name == "acme-voice.md"
    assert "ONE question at a time" in text
    assert "Why 0.50 and not 0.85?" in text
    assert "names cosine profiling" in text, "rubric must be present as interviewer key"
    # Line-wrap agnostic: the template hard-wraps, so match on words not phrases.
    flat = " ".join(text.lower().split())
    assert "do not read this aloud" in flat
    assert "never read the key points aloud" in flat
    # Technical content only: English must not be graded.
    assert "grammar" in text.lower() and "accent" in text.lower()


def test_voice_prompt_is_written_by_the_interview_run(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "writer_call", lambda s, u: VALID)
    monkeypatch.setattr(pipeline, "critic_call", lambda s, u: CRITIC_OK)
    pipeline.run_interview(
        state=State(),
        profile=PROFILE,
        jd=JD,
        jd_slug="acme",
        vault_root=tmp_path,
        today="2026-09-12",
    )
    assert (tmp_path / "interview" / "acme-voice.md").exists()


WITHOUT_QA_SECTION = """---
vaga: "Acme - Senior AI Engineer"
cards:
  - q: "Your RAG returns a stale answer. Retrieval or prompt? How do you tell?"
    a: |
      - Names retrieval as the first suspect and says why
      - Gives a concrete check that separates the two layers
      - States a number: latency, chunk count or similarity threshold
---

## Summary

The posting asks for LoRA fine-tuning, which the profile marks as a gap.
"""


def test_interview_parses_without_a_duplicated_qa_section():
    """The writer stopped writing every question twice.

    The `## Interview Q&A` section was the cards again in prose - same question
    verbatim, rubric reworded - which doubled a 4000-token document and was the
    dominant cause of truncation: six of eleven technical failures cut off
    mid-rubric. The section is rendered from the cards at write time instead.
    """
    parsed = parse_interview_output(WITHOUT_QA_SECTION)
    assert len(parsed["cards"]) == 1
    assert "LoRA" in parsed["summary"]


def test_the_written_file_still_has_the_qa_section(tmp_path):
    """Rendered, not requested. The reader sees no difference."""
    from atlas_sage.vault import write_entry

    parsed = parse_interview_output(WITHOUT_QA_SECTION)
    path = write_entry(
        root=tmp_path,
        nicho="interview",
        slug="acme",
        title="Acme - Senior AI Engineer",
        created="2026-09-14",
        parsed=parsed,
    )
    text = path.read_text(encoding="utf-8")
    assert "## Interview Q&A" in text
    assert "Your RAG returns a stale answer" in text
    assert "Names retrieval as the first suspect" in text
