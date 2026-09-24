from pathlib import Path

from atlas_sage.anki import _guid, export


def _make_entry(root: Path, nicho: str, slug: str, cards: list[dict]) -> None:
    d = root / nicho
    d.mkdir(parents=True, exist_ok=True)
    import yaml

    fm = yaml.safe_dump(
        {
            "title": slug,
            "nicho": nicho,
            "slug": slug,
            "created": "2026-05-27",
            "sources": ["https://example.com/x"],
            "cards": cards,
        },
        sort_keys=False,
    ).strip()
    (d / f"{slug}.md").write_text(
        f"---\n{fm}\n---\n\n## Summary\n\nx\n\n## Interview Q&A\n\nq\n"
    )


def test_export_builds_apkg(tmp_path: Path):
    vault = tmp_path / "vault"
    _make_entry(
        vault,
        "llms",
        "attention-basics",
        [{"q": "What is attention?", "a": "Weighted sum over inputs."}],
    )
    _make_entry(
        vault,
        "java",
        "virtual-threads",
        [
            {"q": "What is a virtual thread?", "a": "JVM-scheduled thread."},
            {"q": "Trade-offs?", "a": "Cheap blocking I/O."},
        ],
    )

    out = tmp_path / "exports" / "career-wiki.apkg"
    counts = export(vault, out)

    assert out.exists()
    assert out.stat().st_size > 0
    assert counts == {"llms": 1, "java": 2}


def test_export_skips_unknown_nicho(tmp_path: Path):
    vault = tmp_path / "vault"
    _make_entry(vault, "blockchain", "x", [{"q": "?", "a": "."}])
    out = tmp_path / "exports" / "career-wiki.apkg"
    counts = export(vault, out)
    assert counts == {}


def test_guid_stable():
    g1 = _guid("llms", "attention", "What is X?")
    g2 = _guid("llms", "attention", "What is X?")
    g3 = _guid("llms", "attention", "What is Y?")
    assert g1 == g2
    assert g1 != g3


def test_export_skips_entries_without_cards(tmp_path: Path):
    vault = tmp_path / "vault"
    _make_entry(vault, "rag", "no-cards", [])
    out = tmp_path / "exports" / "career-wiki.apkg"
    counts = export(vault, out)
    assert counts == {}
