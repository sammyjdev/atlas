import pytest

from atlas_sage.parser import (
    ParseError,
    parse_critic_output,
    parse_writer_output,
)

WRITER_SAMPLE = """---
sources_cited:
  - https://openjdk.org/jeps/444
  - https://inside.java/2023/x
cards:
  - q: "What problem do virtual threads solve?"
    a: "Cheap concurrent I/O-bound tasks without paying for an OS thread per task."
  - q: "Who schedules virtual threads?"
    a: "The JVM, onto carrier OS threads."
---

## Summary

Virtual threads are a lightweight concurrency primitive introduced in Java 21.[^1]

## Interview Q&A

**Q: What is a virtual thread?**
A: A user-mode thread scheduled by the JVM.[^1]

**Q: How are they different from platform threads?**
A: Platform threads map 1:1 to OS threads; virtual threads multiplex onto carriers.[^2]
"""


def test_parse_writer_output_basic():
    parsed = parse_writer_output(WRITER_SAMPLE)
    assert parsed["sources_cited"] == [
        "https://openjdk.org/jeps/444",
        "https://inside.java/2023/x",
    ]
    assert len(parsed["cards"]) == 2
    assert parsed["cards"][0]["q"].startswith("What problem")
    assert "Virtual threads are a lightweight" in parsed["summary"]
    assert "## Interview Q&A" not in parsed["summary"]
    assert "What is a virtual thread" in parsed["qa"]
    assert "## Summary" not in parsed["qa"]


def test_parse_writer_output_missing_frontmatter():
    with pytest.raises(ParseError):
        parse_writer_output("## Summary\nno frontmatter\n")


def test_parse_writer_output_missing_sections():
    bad = """---
sources_cited: []
cards: []
---
just prose, no sections
"""
    with pytest.raises(ParseError):
        parse_writer_output(bad)


def test_parse_critic_approved():
    raw = '{"approved": true, "confidence": "high", "issues": []}'
    r = parse_critic_output(raw)
    assert r.approved is True
    assert r.confidence == "high"
    assert r.issues == []
    assert r.decision_accepts() is True


def test_parse_critic_rejected_low_confidence():
    raw = '{"approved": true, "confidence": "low", "issues": []}'
    r = parse_critic_output(raw)
    assert r.decision_accepts() is False  # low confidence == reject


def test_parse_critic_rejected_explicit():
    raw = '{"approved": false, "confidence": "high", "issues": [{"location":"Summary","problem":"x","severity":"major"}]}'
    r = parse_critic_output(raw)
    assert r.decision_accepts() is False


def test_parse_critic_extracts_json_from_prose():
    raw = 'Here is my review:\n```json\n{"approved": true, "confidence": "med", "issues": []}\n```\nThanks!'
    r = parse_critic_output(raw)
    assert r.approved is True


def test_parse_critic_invalid_raises():
    with pytest.raises(ParseError):
        parse_critic_output("totally not json")


def test_parse_writer_strips_preamble():
    raw = "Sure, here is the document:\n\n" + WRITER_SAMPLE
    parsed = parse_writer_output(raw)
    assert len(parsed["cards"]) == 2
    assert "Virtual threads are a lightweight" in parsed["summary"]


def test_parse_writer_strips_code_fence():
    raw = "```markdown\n" + WRITER_SAMPLE + "\n```"
    parsed = parse_writer_output(raw)
    assert len(parsed["cards"]) == 2


def test_parse_writer_missing_closing_delim():
    raw = """---
sources_cited:
  - https://example.com/a
cards:
  - q: "What?"
    a: "Answer."
## Summary

Body of summary.[^1]

## Interview Q&A

**Q: Foo?**
A: Bar.[^1]
"""
    parsed = parse_writer_output(raw)
    assert parsed["sources_cited"] == ["https://example.com/a"]
    assert parsed["cards"] == [{"q": "What?", "a": "Answer."}]
    assert "Body of summary" in parsed["summary"]
    assert "Foo" in parsed["qa"]


WRITER_NO_CITES = """---
sources_cited:
  - https://openjdk.org/jeps/444
cards:
  - q: "Q?"
    a: "A."
---

## Summary

Virtual threads are lightweight, with no citations at all.

## Interview Q&A

**Q: What?**
A: An uncited answer.
"""


def test_parse_writer_rejects_missing_citations():
    with pytest.raises(ParseError):
        parse_writer_output(WRITER_NO_CITES)


def test_parse_writer_rejects_zero_index_citation():
    doc = """---
sources_cited:
  - https://openjdk.org/jeps/444
cards:
  - q: "Q?"
    a: "A."
---

## Summary

Virtual threads are lightweight.[^0]

## Interview Q&A

**Q: What?**
A: An answer.[^0]
"""
    with pytest.raises(ParseError):
        parse_writer_output(doc)


def test_structural_parse_errors_carry_evidence():
    """A parse failure must say what it got, not only what it wanted.

    Three interviews died on writer_parse in one batch and left nothing behind
    but the rule that fired: state.json recorded "no body section found after
    frontmatter" and the model output was dropped. That is not enough to tell a
    truncated response from a malformed one, and re-running only reproduces it
    if the model misbehaves the same way twice.
    """
    truncated = "---\nvaga: Some Role\ncards:\n  - q: A question that never clo"
    with pytest.raises(ParseError) as exc:
        parse_writer_output(truncated)
    msg = str(exc.value)
    assert f"{len(truncated)} chars" in msg, msg
    assert "never clo" in msg, "the tail is where truncation shows"


def test_critic_parse_error_carries_evidence():
    with pytest.raises(ParseError) as exc:
        parse_critic_output('{"approved": true, "confidence": "high", "issues": [}')
    msg = str(exc.value)
    assert "chars" in msg, msg
    assert "issues" in msg, msg
