from pathlib import Path

from atlas_sage.jds import _topic_keywords, load_jds, match_topics, prioritize_gaps


def test_load_jds_reads_md_and_txt(tmp_path: Path):
    (tmp_path / "a.md").write_text("Senior Java Engineer")
    (tmp_path / "b.txt").write_text("Kafka and Spring")
    (tmp_path / "c.pdf").write_text("ignored")
    texts = load_jds(tmp_path)
    assert len(texts) == 2
    assert all(t == t.lower() for t in texts)
    joined = " ".join(texts)
    assert "java" in joined and "kafka" in joined


def test_load_jds_missing_dir_returns_empty(tmp_path: Path):
    assert load_jds(tmp_path / "nope") == []


def test_topic_keywords_drops_stopwords_and_short():
    kws = _topic_keywords("hybrid search (BM25 + dense)")
    assert "hybrid" in kws
    assert "search" in kws
    assert "dense" in kws
    assert "bm25" in kws
    assert "of" not in kws


def test_match_topics_finds_relevant():
    syllabus = [
        {"topic": "virtual threads (JEP 444)", "nicho": "java"},
        {"topic": "attention mechanism", "nicho": "llms"},
    ]
    jd = ["we need someone strong in virtual threads and loom concurrency"]
    matched = match_topics(jd, syllabus)
    assert {"topic": "virtual threads (JEP 444)", "nicho": "java"} in matched
    assert {"topic": "attention mechanism", "nicho": "llms"} not in matched


def test_match_topics_empty_jd_returns_empty():
    syllabus = [{"topic": "virtual threads", "nicho": "java"}]
    assert match_topics([], syllabus) == []


def test_match_topics_word_boundary_rejects_substring():
    # 'rag' appears only inside 'storage' and 'drag' - never as a whole word.
    # A naive substring matcher would falsely match; whole-word matching must not.
    syllabus = [{"topic": "rag", "nicho": "rag"}]
    jd = ["cloud storage and drag racing experience"]
    assert match_topics(jd, syllabus, min_hits=1) == []


def test_prioritize_gaps_jd_first():
    gaps = [
        {"topic": "records and sealed classes", "nicho": "java"},
        {"topic": "virtual threads (JEP 444)", "nicho": "java"},
    ]
    jd = ["we need virtual threads and loom experience"]
    ordered = prioritize_gaps(gaps, jd)
    assert ordered[0] == ({"topic": "virtual threads (JEP 444)", "nicho": "java"}, "jd")
    assert ordered[1] == (
        {"topic": "records and sealed classes", "nicho": "java"},
        "syllabus",
    )


def test_prioritize_gaps_no_jd_all_syllabus():
    gaps = [{"topic": "virtual threads (JEP 444)", "nicho": "java"}]
    ordered = prioritize_gaps(gaps, [])
    assert ordered == [
        ({"topic": "virtual threads (JEP 444)", "nicho": "java"}, "syllabus")
    ]


def test_pending_jds_skips_the_ones_already_done(tmp_path):
    from atlas_sage.jds import pending_jds

    (tmp_path / "acme-ai-engineer.md").write_text("# Acme\nLoRA required.")
    (tmp_path / "globex-ml-lead.md").write_text("# Globex\nRAG required.")
    (tmp_path / "notes.json").write_text('{"ignored": "wrong suffix"}')

    pending = pending_jds(tmp_path, done=["interview:acme-ai-engineer"])

    assert [slug for slug, _ in pending] == ["globex-ml-lead"]
    assert "RAG required" in pending[0][1]


def test_pending_jds_skips_permanently_failed_ones(tmp_path):
    from atlas_sage.jds import pending_jds

    (tmp_path / "acme-ai-engineer.md").write_text("# Acme")
    assert pending_jds(tmp_path, done=["__failed__:interview:acme-ai-engineer"]) == []


def test_pending_jds_on_missing_dir_is_empty(tmp_path):
    from atlas_sage.jds import pending_jds

    assert pending_jds(tmp_path / "nope", done=[]) == []


def test_pending_is_computed_per_track(tmp_path):
    """A posting already interviewed technically is still pending for screening.

    The two tracks are different conversations about the same job, so one key
    prefix must not hide a posting from the other.
    """
    from atlas_sage.jds import pending_jds

    jds = tmp_path / "jds"
    jds.mkdir()
    (jds / "acme.md").write_text("Senior AI Engineer at Acme")
    (jds / "globex.md").write_text("Staff Engineer at Globex")

    done = ["interview:acme", "__failed__:screening:globex"]

    technical = [s for s, _ in pending_jds(jds, done)]
    assert technical == ["globex"]

    screening = [s for s, _ in pending_jds(jds, done, key_prefix="screening")]
    assert screening == ["acme"]
