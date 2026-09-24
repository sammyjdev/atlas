import json
import sys
from pathlib import Path

from atlas_sage import main, pipeline

WRITER_OUT = """---
sources_cited:
  - https://openjdk.org/jeps/444
cards:
  - q: "What are virtual threads?"
    a: "User-mode threads scheduled by the JVM."
---

## Summary

Virtual threads are lightweight concurrency primitives.[^1]

## Interview Q&A

**Q: What problem do they solve?**
A: Cheap I/O-bound concurrency.[^1]
"""

CRITIC_OUT = '{"approved": true, "confidence": "high", "issues": []}'


def test_smoke_once_end_to_end(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path))
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "queue": [],
                "done": [],
                "retries": {},
                "usage": {
                    "date": "2026-06-17",
                    "writer_calls": 0,
                    "critic_calls": 0,
                    "tavily_calls": 0,
                },
            }
        )
    )
    syllabus_file = tmp_path / "inputs" / "syllabus.yaml"
    syllabus_file.parent.mkdir()
    syllabus_file.write_text("java:\n  - virtual threads (JEP 444)\n")
    vault = tmp_path / "vault"
    apkg = tmp_path / "exports" / "sage.apkg"

    monkeypatch.setattr(
        pipeline,
        "search",
        lambda topic, nicho, api_key: [
            {
                "url": "https://openjdk.org/jeps/444",
                "content": "JEP 444 introduces virtual threads.",
            },
            {"url": "https://inside.java/a", "content": "..."},
            {"url": "https://inside.java/b", "content": "..."},
        ],
    )
    monkeypatch.setattr(pipeline, "writer_call", lambda s, u: WRITER_OUT)
    monkeypatch.setattr(pipeline, "critic_call", lambda s, u: CRITIC_OUT)
    monkeypatch.setenv("TAVILY_API_KEY", "x")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("NVIDIA_API_KEY", "x")
    monkeypatch.setattr(sys, "argv", ["sage", "--once"])

    rc = main.cli()

    assert rc == 0
    entry = vault / "java" / "virtual-threads-jep-444.md"
    assert entry.exists()
    assert (vault / "java" / "virtual-threads-jep-444-qa.md").exists()
    # the entry is really rendered: sections + a resolved inline citation footnote
    entry_text = entry.read_text(encoding="utf-8")
    assert "## Summary" in entry_text
    assert "[^1]: https://openjdk.org/jeps/444" in entry_text
    saved = json.loads(state_file.read_text())
    assert "virtual-threads-jep-444" in saved["done"]
    assert apkg.exists()
