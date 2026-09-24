from pathlib import Path

from atlas_sage import pipeline
from atlas_sage.state import MAX_RETRIES, State

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


def test_run_once_happy_path(tmp_path: Path, monkeypatch):
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

    state = State(
        queue=[
            {
                "topic": "JVM virtual threads",
                "nicho": "java",
                "source": "syllabus",
                "added": "2026-05-27",
            }
        ]
    )

    result = pipeline.run_once(state=state, vault_root=tmp_path, today="2026-05-27")

    assert result["status"] == "approved"
    assert result["slug"] == "jvm-virtual-threads"
    assert (tmp_path / "java" / "jvm-virtual-threads.md").exists()
    assert (tmp_path / "java" / "jvm-virtual-threads-qa.md").exists()
    assert "jvm-virtual-threads" in state.done
    assert state.queue == []
    assert state.usage["writer_calls"] == 1
    assert state.usage["critic_calls"] == 1


def test_run_once_insufficient_sources(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "search",
        lambda topic, nicho, api_key: [
            {"url": "https://openjdk.org/x", "content": "x"}
        ],
    )
    monkeypatch.setenv("TAVILY_API_KEY", "x")

    state = State(
        queue=[
            {
                "topic": "JVM virtual threads",
                "nicho": "java",
                "source": "syllabus",
                "added": "2026-05-27",
            }
        ]
    )
    result = pipeline.run_once(state=state, vault_root=tmp_path, today="2026-05-27")

    assert result["status"] == "failed"
    assert result["reason"] == "no_quality_sources"
    assert "__failed__:jvm-virtual-threads" in state.done


def test_run_once_critic_rejects(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "search",
        lambda topic, nicho, api_key: [
            {"url": "https://openjdk.org/jeps/444", "content": "..."},
            {"url": "https://inside.java/a", "content": "..."},
            {"url": "https://inside.java/b", "content": "..."},
        ],
    )
    monkeypatch.setattr(pipeline, "writer_call", lambda s, u: WRITER_OUT)
    monkeypatch.setattr(
        pipeline,
        "critic_call",
        lambda s, u: '{"approved": false, "confidence": "high", "issues": [{"location":"Summary","problem":"x","severity":"major"}]}',
    )
    monkeypatch.setenv("TAVILY_API_KEY", "x")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("NVIDIA_API_KEY", "x")

    state = State(
        queue=[
            {
                "topic": "JVM virtual threads",
                "nicho": "java",
                "source": "syllabus",
                "added": "2026-05-27",
            }
        ]
    )
    result = pipeline.run_once(state=state, vault_root=tmp_path, today="2026-05-27")

    assert result["status"] == "rejected"
    assert state.retries["jvm-virtual-threads"] == 1
    assert len(state.queue) == 1  # still queued for retry
    # the rejection fires one in-run revision: 2 writer calls, 2 critic calls
    assert state.usage["writer_calls"] == 2
    assert state.usage["critic_calls"] == 2


def test_run_once_both_rounds_reject_marks_failed(tmp_path: Path, monkeypatch):
    # On the final retry (retries already at MAX_RETRIES - 1), a draft that is
    # rejected by both the initial critic and the post-revision critic must be
    # marked __failed__ with a recorded reason.
    monkeypatch.setattr(
        pipeline,
        "search",
        lambda topic, nicho, api_key: [
            {"url": "https://openjdk.org/jeps/444", "content": "..."},
            {"url": "https://inside.java/a", "content": "..."},
            {"url": "https://inside.java/b", "content": "..."},
        ],
    )
    monkeypatch.setattr(pipeline, "writer_call", lambda s, u: WRITER_OUT)
    monkeypatch.setattr(
        pipeline,
        "critic_call",
        lambda s, u: '{"approved": false, "confidence": "high", "issues": [{"location":"Summary","problem":"x","severity":"major"}]}',
    )
    monkeypatch.setenv("TAVILY_API_KEY", "x")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("NVIDIA_API_KEY", "x")

    state = State(
        queue=[
            {
                "topic": "JVM virtual threads",
                "nicho": "java",
                "source": "syllabus",
                "added": "2026-05-27",
            }
        ],
        retries={"jvm-virtual-threads": MAX_RETRIES - 1},
    )
    result = pipeline.run_once(state=state, vault_root=tmp_path, today="2026-05-27")

    assert result["status"] == "rejected"
    assert "__failed__:jvm-virtual-threads" in state.done
    assert state.queue == []
    assert state.failures["jvm-virtual-threads"]["reason"] == "critic"


def test_run_once_empty_queue_returns_idle(tmp_path: Path):
    state = State()
    result = pipeline.run_once(state=state, vault_root=tmp_path, today="2026-05-27")
    assert result["status"] == "idle"


def test_run_once_revise_recovers(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "search",
        lambda topic, nicho, api_key: [
            {"url": "https://openjdk.org/jeps/444", "content": "JEP 444."},
            {"url": "https://inside.java/a", "content": "..."},
            {"url": "https://inside.java/b", "content": "..."},
        ],
    )
    monkeypatch.setattr(pipeline, "writer_call", lambda s, u: WRITER_OUT)
    critic_responses = iter(
        [
            '{"approved": false, "confidence": "high", "issues": [{"location":"Summary","problem":"x","severity":"major"}]}',
            '{"approved": true, "confidence": "high", "issues": []}',
        ]
    )
    monkeypatch.setattr(pipeline, "critic_call", lambda s, u: next(critic_responses))
    monkeypatch.setenv("TAVILY_API_KEY", "x")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("NVIDIA_API_KEY", "x")

    state = State(
        queue=[
            {
                "topic": "JVM virtual threads",
                "nicho": "java",
                "source": "syllabus",
                "added": "2026-05-27",
            }
        ]
    )
    result = pipeline.run_once(state=state, vault_root=tmp_path, today="2026-05-27")

    assert result["status"] == "approved"
    assert state.usage["writer_calls"] == 2
    assert state.usage["critic_calls"] == 2
    entry = tmp_path / "java" / "jvm-virtual-threads.md"
    assert entry.exists()
    assert "[^1]: https://openjdk.org/jeps/444" in entry.read_text()
