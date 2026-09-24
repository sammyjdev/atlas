from atlas_sage.corpus import (
    ALLOWED_LICENSES,
    MIN_SOURCES_FOR_COMMON,
    extract_questions,
    is_translation,
    license_allows_reuse,
    normalize_question,
    rank_by_recurrence,
    survives_normalization,
)


def test_license_gate_admits_permissive_and_refuses_the_rest():
    for spdx in ("MIT", "Apache-2.0", "CC0-1.0", "BSD-3-Clause"):
        assert license_allows_reuse(spdx), spdx
    for spdx in ("GPL-3.0", "AGPL-3.0", "CC-BY-NC-4.0", "", None, "NOASSERTION"):
        assert not license_allows_reuse(spdx), spdx


def test_license_gate_is_case_and_whitespace_insensitive():
    assert license_allows_reuse("  mit  ")
    assert "mit" in ALLOWED_LICENSES


def test_normalize_collapses_the_cosmetic_differences():
    """Recurrence only works if the same question in two repos hashes the same."""
    variants = [
        "What is React?",
        "what is react",
        "  What   is  React ?  ",
        "**What is React?**",
        "1. What is React?",
        "- What is React?",
    ]
    assert len({normalize_question(v) for v in variants}) == 1


def test_normalize_keeps_genuinely_different_questions_apart():
    a = normalize_question("What is a closure?")
    b = normalize_question("What is a coroutine?")
    assert a != b


def test_extract_questions_pulls_interrogatives_from_markdown():
    md = """
# Python Questions

1. What is the GIL?
2. Explain list comprehension.

Some prose that is not a question.

- How do you profile a slow function?

```python
# What is this? (inside a code fence, must be ignored)
```
"""
    found = extract_questions(md)
    assert "What is the GIL?" in found
    assert "How do you profile a slow function?" in found
    assert not any("inside a code fence" in q for q in found)
    assert not any("Some prose" in q for q in found)


def test_rank_by_recurrence_counts_distinct_sources_not_occurrences():
    """A question repeated 50x in one repo is not more common than one in 5 repos."""
    harvested = [
        ("repoA", "What is React?"),
        ("repoA", "What is React?"),
        ("repoA", "What is React?"),
        ("repoB", "what is react"),
        ("repoC", "What is a monad?"),
    ]
    ranked = rank_by_recurrence(harvested)
    by_text = {r["question"]: r for r in ranked}
    react = by_text[normalize_question("What is React?")]
    assert react["sources"] == 2, "three copies in repoA count once"
    assert set(react["seen_in"]) == {"repoA", "repoB"}
    assert ranked[0]["sources"] >= ranked[-1]["sources"], "ranked descending"


def test_translated_paths_are_excluded_before_they_are_fetched():
    """The corpus is English, and a translation is the same question again.

    A Portuguese question is almost pure ASCII, so no content rule finds it after
    the fact. The path does, and it also stops one question translated five times
    from counting as five - which would inflate the recurrence being measured.
    """
    for path in (
        "pt-br/README.md",
        "translations/pt/questions.md",
        "i18n/es/index.md",
        "docs/ko/interview.md",
        "README.zh-CN.md",
        "locales/ja/faq.json",
    ):
        assert is_translation(path), path

    for path in (
        "README.md",
        "questions/javascript.md",
        "docs/system-design.md",
        "data/questions.json",
    ):
        assert not is_translation(path), path


def test_a_question_gutted_by_normalization_is_refused():
    """192 Korean questions entered the first harvest as one-token stubs.

    '.Net의 개체 풀이란 무엇입니까?' has four raw words, clears the word floor,
    and normalizes to 'net' - which then overlaps with every candidate that
    mentions .NET.
    """
    md = "- .Net의 개체 풀이란 무엇입니까?\n- What is connection pooling in .NET?\n"
    assert extract_questions(md) == ["What is connection pooling in .NET?"]


def test_a_short_english_question_is_kept():
    """The rule measures script, not length.

    "What is React?" is three words and is the most recitable question there is;
    a word floor would throw it away along with the stubs, and a fraction of
    surviving words keeps 'ArrayList와 LinkedList의 차이점은 무엇입니까?' because
    Korean agglutinates its particle onto the Latin term.
    """
    assert survives_normalization("What is React?")
    assert not survives_normalization(".Net의 개체 풀이란 무엇입니까?")
    assert not survives_normalization("ArrayList와 LinkedList의 차이점은 무엇입니까?")


def test_rank_refuses_gutted_entries_from_any_extractor():
    """The rank is the one gate both extractors drain into.

    extract_questions_from_json applies no rule of its own, so a source shipping
    questions as JSON would otherwise reintroduce the defect.
    """
    harvested = [
        ("repoA", "closure를 사용하여 개인 카운터를 만드는 방법은 무엇입니까?"),
        ("repoA", "What is the difference between a closure and a callback?"),
    ]
    ranked = rank_by_recurrence(harvested)
    assert [r["question"] for r in ranked] == [
        normalize_question("What is the difference between a closure and a callback?")
    ]


def test_presence_not_recurrence_is_the_default_threshold():
    """Measured, not assumed: 3352 distinct questions yielded 27 recurring ones.

    Requiring recurrence across families threw away 99.2% of the corpus. A
    question published in one popular repo is already recitable.
    """
    assert MIN_SOURCES_FOR_COMMON == 1


def test_recurrence_counts_editorial_families_not_repositories():
    """Two repos by the same author are one origin, not two.

    KalyanKS-NLP publishes an LLM hub and a RAG hub; yangshun/front-end and
    vagasfrontend both descend from h5bp. Counting repos would inflate the very
    number the recitability filter rests on.
    """
    from atlas_sage.corpus import rank_by_recurrence_by_family

    harvested = [
        ("KalyanKS-NLP/LLM-Hub", "What is attention?"),
        ("KalyanKS-NLP/RAG-Hub", "What is attention?"),
        ("amitshekhariitbhu/ai-eng", "What is attention?"),
    ]
    families = {
        "KalyanKS-NLP/LLM-Hub": "kalyanks",
        "KalyanKS-NLP/RAG-Hub": "kalyanks",
        "amitshekhariitbhu/ai-eng": "amitshekhar",
    }
    ranked = rank_by_recurrence_by_family(harvested, families)
    row = ranked[0]
    assert row["sources"] == 2, f"two families, not three repos: {row}"
    assert set(row["families"]) == {"kalyanks", "amitshekhar"}
    assert len(row["seen_in"]) == 3, "repos are still recorded for provenance"


def test_family_defaults_to_the_repo_when_unmapped():
    from atlas_sage.corpus import rank_by_recurrence_by_family

    ranked = rank_by_recurrence_by_family([("solo/repo", "What is a monad?")], {})
    assert ranked[0]["sources"] == 1
    assert ranked[0]["families"] == ["solo/repo"]


def test_extract_rejects_generic_document_headings():
    """ "## What is this?" is a README heading, not an interview question.

    It reached the top of the recurrence ranking in the first real harvest, which
    is how it was found: three repos share a boilerplate heading.
    """
    md = """
## What is this?
## Why?
### Table of Contents
## How to use
## What is the GIL and why does it matter for CPU-bound work?
"""
    found = extract_questions(md)
    assert not any("What is this" in q for q in found)
    assert not any(q.strip().lower().startswith("why?") for q in found)
    assert any("GIL" in q for q in found), "real questions must survive"


def test_extract_rejects_questions_that_are_too_short_to_be_one():
    md = "\n".join(["## Why?", "## How?", "- What?", "What is a race condition?"])
    found = extract_questions(md)
    assert found == ["What is a race condition?"]


def test_extract_questions_from_json_records():
    """dataskew-io ships JSON, not markdown - it returned 0 questions."""
    from atlas_sage.corpus import extract_questions_from_json

    payload = """
    [
      {"question": "How would you design an idempotent ingestion pipeline?", "area": "data"},
      {"q": "What is a watermark in stream processing?"},
      {"title": "not a question field", "body": "ignored"}
    ]
    """
    found = extract_questions_from_json(payload)
    assert "How would you design an idempotent ingestion pipeline?" in found
    assert "What is a watermark in stream processing?" in found
    assert len(found) == 2


def test_extract_from_json_survives_malformed_input():
    from atlas_sage.corpus import extract_questions_from_json

    assert extract_questions_from_json("not json at all") == []
    assert extract_questions_from_json(
        '{"nested": {"question": "Is this found?"}}'
    ) == ["Is this found?"]


def test_unverifiable_license_is_distinct_from_absent_license():
    """A 403 must not be reported as "this repo has no licence".

    Both outcomes skip the source, which is correct, but conflating them sent a
    rate-limit incident out as thirteen false "(none)" verdicts.
    """
    from atlas_sage.corpus import LicenseStatus, classify_license

    assert classify_license("MIT", error=None) is LicenseStatus.ALLOWED
    assert classify_license("GPL-3.0", error=None) is LicenseStatus.REFUSED
    assert classify_license(None, error=None) is LicenseStatus.ABSENT
    assert classify_license(None, error="HTTP 403") is LicenseStatus.UNVERIFIABLE


def test_only_allowed_status_permits_harvesting():
    from atlas_sage.corpus import LicenseStatus

    assert LicenseStatus.ALLOWED.may_harvest
    for status in (
        LicenseStatus.REFUSED,
        LicenseStatus.ABSENT,
        LicenseStatus.UNVERIFIABLE,
    ):
        assert not status.may_harvest, status
