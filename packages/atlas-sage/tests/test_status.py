from pathlib import Path

from atlas_sage.state import State
from atlas_sage.status import render_status, write_status

SYLLABUS = [
    {"topic": "attention mechanism", "nicho": "llms"},
    {"topic": "tokenization (BPE, SentencePiece)", "nicho": "llms"},
    {"topic": "RLHF and preference optimization", "nicho": "llms"},
    {"topic": "virtual threads (JEP 444)", "nicho": "java"},
    {"topic": "JVM memory model", "nicho": "java"},
]


def _state():
    return State(
        queue=[
            {
                "topic": "RLHF and preference optimization",
                "nicho": "llms",
                "source": "jd",
                "added": "2026-06-17",
            }
        ],
        done=[
            "attention-mechanism",
            "__failed__:tokenization-bpe-sentencepiece",
            "virtual-threads-jep-444",
        ],
        failures={
            "tokenization-bpe-sentencepiece": {"reason": "critic", "date": "2026-05-28"}
        },
        usage={
            "date": "2026-06-17",
            "writer_calls": 2,
            "critic_calls": 2,
            "tavily_calls": 1,
        },
    )


def test_render_status_coverage_counts():
    out = render_status(_state(), SYLLABUS)
    # llms: 3 topics total, 1 done, 1 failed, 1 remaining
    assert "| llms | 1 | 1 | 1 | 3 |" in out
    # java: 2 topics total, 1 done, 0 failed, 1 remaining
    assert "| java | 1 | 0 | 1 | 2 |" in out


def test_render_status_failures_with_and_without_reason():
    out = render_status(_state(), SYLLABUS)
    # known reason from the failures map
    assert "tokenization-bpe-sentencepiece" in out
    assert "critic" in out
    assert "2026-05-28" in out


def test_render_status_failure_without_recorded_reason():
    st = _state()
    st.done.append("__failed__:mystery-topic")
    # add it to syllabus so it is counted, but no failures entry
    syl = SYLLABUS + [{"topic": "mystery topic", "nicho": "llms"}]
    out = render_status(st, syl)
    assert "mystery-topic" in out
    assert "reason not recorded" in out


def test_render_status_queue_and_usage():
    out = render_status(_state(), SYLLABUS)
    assert "1 topic" in out  # queue length
    assert "RLHF and preference optimization" in out
    assert "writer calls: 2" in out
    assert "tavily calls: 1" in out


def test_render_status_no_failures():
    st = State(done=["attention-mechanism"], usage={"date": "2026-06-17"})
    out = render_status(st, SYLLABUS)
    assert "None." in out  # failures section empty


def test_render_status_real_path_failures_map_absent():
    # mirrors the live state.json: __failed__ entries present, no failures map yet
    st = State(
        done=[
            "attention-mechanism",
            "__failed__:tokenization-bpe-sentencepiece",
        ],
        usage={"date": "2026-06-17"},
    )
    out = render_status(st, SYLLABUS)
    assert "tokenization-bpe-sentencepiece" in out
    assert "reason not recorded" in out


def test_write_status_writes_file(tmp_path: Path):
    p = tmp_path / "STATUS.md"
    content = write_status(p, _state(), SYLLABUS)
    assert p.exists()
    assert p.read_text(encoding="utf-8") == content
    assert content.startswith("# SAGE Status")
