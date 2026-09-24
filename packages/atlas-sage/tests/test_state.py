import json
from pathlib import Path

from atlas_sage.state import (
    MAX_RETRIES,
    State,
    load,
    record_done,
    record_failed,
    record_retry,
    save,
    slug,
)


def test_round_trip(tmp_path: Path):
    p = tmp_path / "state.json"
    s = State(
        queue=[
            {
                "topic": "JVM virtual threads",
                "nicho": "java",
                "source": "syllabus",
                "added": "2026-05-27",
            }
        ],
        done=["rag-chunking"],
        retries={"jvm-classloaders": 1},
        usage={
            "date": "2026-05-27",
            "writer_calls": 3,
            "critic_calls": 3,
            "tavily_calls": 3,
        },
    )
    save(p, s)
    loaded = load(p)
    assert loaded == s


def test_load_missing_file_returns_empty(tmp_path: Path):
    s = load(tmp_path / "nope.json")
    assert s.queue == []
    assert s.done == []
    assert s.retries == {}
    assert s.usage["writer_calls"] == 0


def test_record_done_moves_from_queue():
    s = State(
        queue=[
            {"topic": "X", "nicho": "java", "source": "syllabus", "added": "2026-05-27"}
        ]
    )
    record_done(s, "x")
    assert s.done == ["x"]
    assert s.queue == []
    assert "x" not in s.retries


def test_record_retry_increments_and_keeps_in_queue():
    item = {"topic": "X", "nicho": "java", "source": "syllabus", "added": "2026-05-27"}
    s = State(queue=[item])
    record_retry(s, "x")
    assert s.retries["x"] == 1
    assert s.queue == [item]


def test_record_retry_at_max_marks_failed_and_removes():
    item = {"topic": "X", "nicho": "java", "source": "syllabus", "added": "2026-05-27"}
    s = State(queue=[item], retries={"x": MAX_RETRIES - 1})
    record_retry(s, "x")
    assert s.queue == []
    assert "__failed__:x" in s.done
    assert "x" not in s.retries


def test_record_retry_at_max_records_reason():
    s = State(
        queue=[
            {"topic": "X", "nicho": "java", "source": "syllabus", "added": "2026-05-27"}
        ],
        retries={"x": MAX_RETRIES - 1},
    )
    record_retry(s, "x", reason="critic")
    assert "__failed__:x" in s.done
    assert s.failures["x"]["reason"] == "critic"
    assert "date" in s.failures["x"]


def test_record_retry_below_max_does_not_record_reason():
    s = State(
        queue=[
            {"topic": "X", "nicho": "java", "source": "syllabus", "added": "2026-05-27"}
        ]
    )
    record_retry(s, "x", reason="critic")
    assert s.failures == {}


def test_record_failed_marks_and_records_reason():
    item = {"topic": "X", "nicho": "java", "source": "syllabus", "added": "2026-05-27"}
    s = State(queue=[item])
    record_failed(s, "x", reason="no_quality_sources")
    assert s.queue == []
    assert "__failed__:x" in s.done
    assert "x" not in s.retries
    assert s.failures["x"]["reason"] == "no_quality_sources"


def test_record_done_clears_prior_failure():
    s = State(
        queue=[
            {"topic": "X", "nicho": "java", "source": "syllabus", "added": "2026-05-27"}
        ],
        failures={"x": {"reason": "critic", "date": "2026-05-28"}},
    )
    record_done(s, "x")
    assert "x" not in s.failures


def test_load_backfills_failures_for_old_state(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"queue": [], "done": ["__failed__:x"], "retries": {}}))
    s = load(p)
    assert s.failures == {}


def test_slug_lowercases_and_kebabs():
    assert slug("JVM Virtual Threads") == "jvm-virtual-threads"
    assert slug("RAG: Chunking Strategies") == "rag-chunking-strategies"
    assert slug("  attention basics  ") == "attention-basics"
