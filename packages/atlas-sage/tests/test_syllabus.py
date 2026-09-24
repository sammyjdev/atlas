import textwrap
from pathlib import Path

from atlas_sage.syllabus import find_gaps, load_syllabus


def test_load_syllabus(tmp_path: Path):
    p = tmp_path / "syllabus.yaml"
    p.write_text(textwrap.dedent("""
        llms:
          - attention basics
          - tokenization
        java:
          - virtual threads
    """))
    items = load_syllabus(p)
    assert items == [
        {"topic": "attention basics", "nicho": "llms"},
        {"topic": "tokenization", "nicho": "llms"},
        {"topic": "virtual threads", "nicho": "java"},
    ]


def test_find_gaps_excludes_done_and_queued():
    syllabus = [
        {"topic": "attention basics", "nicho": "llms"},
        {"topic": "tokenization", "nicho": "llms"},
        {"topic": "virtual threads", "nicho": "java"},
    ]
    done = ["attention-basics"]
    queued = [{"topic": "Tokenization", "nicho": "llms"}]
    gaps = find_gaps(syllabus, done, queued)
    assert gaps == [{"topic": "virtual threads", "nicho": "java"}]


def test_find_gaps_excludes_failed_done():
    syllabus = [{"topic": "attention basics", "nicho": "llms"}]
    done = ["__failed__:attention-basics"]
    assert find_gaps(syllabus, done, []) == []
