from __future__ import annotations

import hashlib
from pathlib import Path

import genanki
import yaml

MODEL_ID = 1759830482
NICHO_DECK_IDS = {
    "llms": 2059400110,
    "rag": 2059400111,
    "java": 2059400112,
    # Adversarial interview questions: front is the question, back is the rubric.
    "interview": 2059400113,
}
DECK_ROOT = "SAGE"

MODEL = genanki.Model(
    model_id=MODEL_ID,
    name="sage",
    fields=[
        {"name": "Question"},
        {"name": "Answer"},
        {"name": "Source"},
    ],
    templates=[
        {
            "name": "Card",
            "qfmt": "{{Question}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Answer}}<br><br><small>{{Source}}</small>',
        }
    ],
)


def _guid(nicho: str, slug: str, question: str) -> str:
    h = hashlib.sha1(f"{nicho}|{slug}|{question}".encode()).hexdigest()
    return h[:16]


def _read_entry(path: Path) -> dict | None:
    text = path.read_text()
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    try:
        meta = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict):
        return None
    return meta


def export(vault_root: Path, out_path: Path) -> dict:
    decks: dict[str, genanki.Deck] = {}
    counts: dict[str, int] = {}

    for nicho_dir in sorted(p for p in vault_root.iterdir() if p.is_dir()):
        nicho = nicho_dir.name
        for md in sorted(nicho_dir.glob("*.md")):
            meta = _read_entry(md)
            if not meta:
                continue
            slug = meta.get("slug") or md.stem
            cards = meta.get("cards") or []
            sources = meta.get("sources") or []
            source_html = "<br>".join(f'<a href="{s}">{s}</a>' for s in sources)

            deck_id = NICHO_DECK_IDS.get(nicho)
            if deck_id is None:
                continue
            if nicho not in decks:
                decks[nicho] = genanki.Deck(
                    deck_id=deck_id, name=f"{DECK_ROOT}::{nicho}"
                )

            for card in cards:
                q = (card.get("q") or "").strip()
                a = (card.get("a") or "").strip()
                if not q or not a:
                    continue
                note = genanki.Note(
                    model=MODEL,
                    fields=[q, a, source_html],
                    guid=_guid(nicho, slug, q),
                )
                decks[nicho].add_note(note)
                counts[nicho] = counts.get(nicho, 0) + 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    package = genanki.Package(list(decks.values()))
    package.write_to_file(out_path)
    return counts
