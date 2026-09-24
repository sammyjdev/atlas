from pathlib import Path

import yaml

from atlas_sage.vault import write_entry, write_qa

PARSED = {
    "sources_cited": ["https://openjdk.org/jeps/444"],
    "cards": [{"q": "Q1?", "a": "A1."}],
    "summary": "Virtual threads are...",
    "qa": "**Q: ...**\nA: ...",
}


def test_write_entry_creates_file(tmp_path: Path):
    path = write_entry(
        root=tmp_path,
        nicho="java",
        slug="jvm-virtual-threads",
        title="JVM Virtual Threads",
        created="2026-05-27",
        parsed=PARSED,
    )
    assert path == tmp_path / "java" / "jvm-virtual-threads.md"
    text = path.read_text()
    assert text.startswith("---\n")
    fm_end = text.index("\n---\n", 4)
    fm = yaml.safe_load(text[4:fm_end])
    assert fm["title"] == "JVM Virtual Threads"
    assert fm["nicho"] == "java"
    assert fm["slug"] == "jvm-virtual-threads"
    assert fm["created"] == "2026-05-27"
    assert fm["sources"] == ["https://openjdk.org/jeps/444"]
    assert fm["cards"] == [{"q": "Q1?", "a": "A1."}]
    body = text[fm_end + 5 :]
    assert "## Summary" in body
    assert "Virtual threads are..." in body
    assert "## Interview Q&A" in body


PARSED_MULTI = {
    "sources_cited": ["https://openjdk.org/jeps/444"],
    "cards": [
        {
            "q": "What are virtual threads?",
            "a": "User-mode threads scheduled by the JVM.",
        },
        {"q": "Why use them?", "a": "Cheap I/O-bound concurrency."},
    ],
    "summary": "Virtual threads are lightweight.",
    "qa": "**Q: ...**\nA: ...",
}


def test_write_qa_creates_sr_format(tmp_path: Path):
    path = write_qa(
        root=tmp_path,
        nicho="java",
        slug="jvm-virtual-threads",
        title="JVM Virtual Threads",
        created="2026-05-27",
        parsed=PARSED_MULTI,
    )
    assert path == tmp_path / "java" / "jvm-virtual-threads-qa.md"
    text = path.read_text()

    # frontmatter has the related link
    assert "[[jvm-virtual-threads]]" in text

    # flashcards tag present
    assert "#flashcards/java/jvm-virtual-threads" in text

    # each card q and a separated by lone "?"
    assert "What are virtual threads?" in text
    assert "User-mode threads scheduled by the JVM." in text
    assert "Why use them?" in text
    assert "Cheap I/O-bound concurrency." in text

    # separator line is exactly "?"
    lines = text.splitlines()
    assert "?" in lines

    # verify q→?→a ordering for first card
    q_idx = lines.index("What are virtual threads?")
    sep_idx = lines.index("?", q_idx)
    a_line = lines[sep_idx + 1]
    assert "User-mode threads scheduled by the JVM." in a_line


def test_write_entry_renders_footnote_definitions(tmp_path: Path):
    sources = [
        {"url": "https://openjdk.org/jeps/444", "content": "..."},
        {"url": "https://inside.java/a", "content": "..."},
    ]
    path = write_entry(
        root=tmp_path,
        nicho="java",
        slug="vt",
        title="VT",
        created="2026-05-27",
        parsed=PARSED,
        sources=sources,
    )
    text = path.read_text()
    assert "[^1]: https://openjdk.org/jeps/444" in text
    assert "[^2]: https://inside.java/a" in text


def test_transcript_is_on_disk_before_the_session_ends(tmp_path):
    """A 20-minute session that dies on turn 18 must not lose turns 1-17.

    That is the one unrecoverable failure in a live interview: the candidate's
    time cannot be replayed. The fix is appending, not a finalize step.
    """
    from atlas_sage.vault import append_turn, write_session_header

    path = write_session_header(
        root=tmp_path,
        nicho="interview",
        slug="acme",
        title="Acme - Senior AI Engineer",
        created="2026-09-13",
    )
    append_turn(path, "interviewer", "Your RAG returns stale answers. Why?")
    append_turn(path, "candidate", "I would check the index first.")
    append_turn(path, "interviewer", "Which number tells you it is the index?")

    text = path.read_text(encoding="utf-8")
    assert "stale answers" in text
    assert "check the index first" in text
    assert "Which number" in text


def test_session_file_carries_no_cards_key(tmp_path):
    """Load-bearing: `cards:` is what pulls a file into Anki and the label sheet.

    A transcript with that key would land in the Anki deck and in the sheet a
    recruiter fills in about generated question quality.
    """
    from atlas_sage.vault import write_session_header

    path = write_session_header(
        root=tmp_path,
        nicho="interview",
        slug="acme",
        title="Acme",
        created="2026-09-13",
    )
    import yaml

    text = path.read_text(encoding="utf-8")
    meta = yaml.safe_load(text.split("---")[1])
    assert "cards" not in meta
    assert meta["mode"] == "session"
