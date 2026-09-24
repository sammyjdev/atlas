from __future__ import annotations

from pathlib import Path

import yaml


def write_qa(
    root: Path, nicho: str, slug: str, title: str, created: str, parsed: dict
) -> Path:
    out_dir = root / nicho
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slug}-qa.md"

    frontmatter = {
        "title": f"{title} — Q&A",
        "nicho": nicho,
        "slug": slug,
        "created": created,
        "related": f"[[{slug}]]",
    }
    fm_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()

    cards = parsed.get("cards", [])
    card_lines: list[str] = []
    for card in cards:
        q = (card.get("q") or "").strip()
        a = (card.get("a") or "").strip()
        if not q or not a:
            continue
        card_lines.append(q)
        card_lines.append("?")
        card_lines.append(a)
        card_lines.append("")  # blank line between cards

    cards_text = "\n".join(card_lines).strip()

    body = (
        f"---\n{fm_text}\n---\n\n"
        f"#flashcards/{nicho}/{slug}\n\n"
        f"## Interview Q&A\n\n"
        f"{cards_text}\n"
    )
    path.write_text(body)
    return path


def write_entry(
    root: Path,
    nicho: str,
    slug: str,
    title: str,
    created: str,
    parsed: dict,
    sources: list[dict] | None = None,
) -> Path:
    out_dir = root / nicho
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slug}.md"

    frontmatter = {
        "title": title,
        "nicho": nicho,
        "slug": slug,
        "created": created,
        "sources": parsed.get("sources_cited", []),
        "cards": parsed.get("cards", []),
    }
    fm_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()

    body = (
        f"---\n{fm_text}\n---\n\n"
        f"## Summary\n\n{parsed['summary'].strip()}\n\n"
        f"## Interview Q&A\n\n{parsed['qa'].strip()}\n"
    )
    if sources:
        fn_lines = [f"[^{i}]: {s['url']}" for i, s in enumerate(sources, 1)]
        body += "\n" + "\n".join(fn_lines) + "\n"
    path.write_text(body)
    return path


def write_voice_prompt(
    root: Path, nicho: str, slug: str, title: str, created: str, parsed: dict
) -> Path:
    """Render the interview as a paste-ready voice role-play script.

    Template only, no model call: the questions and rubrics already exist, this
    just reframes them as instructions for an interviewer. That keeps the voice
    drill free beyond a subscription the author already pays for.
    """
    from .prompts import VOICE_INTERVIEW_TEMPLATE, format_voice_questions

    out_dir = root / nicho
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slug}-voice.md"
    path.write_text(
        VOICE_INTERVIEW_TEMPLATE.format(
            title=title,
            slug=slug,
            created=created,
            questions_block=format_voice_questions(parsed.get("cards") or []),
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_session_header(
    root: Path, nicho: str, slug: str, title: str, created: str
) -> Path:
    """Open a live session file and return its path.

    Deliberately carries no `cards:` key. That key is what pulls a document into
    the Anki export, the label sheet and the recitability measurement, and a
    transcript belongs in none of the three: it is a record of one conversation,
    not a set of generated questions.
    """
    out_dir = root / nicho
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slug}-session-{created}.md"
    path.write_text(
        f"---\n"
        f'title: "{title} - live session"\n'
        f"slug: {slug}\n"
        f"created: {created}\n"
        f"mode: session\n"
        f"---\n\n"
        f"## Transcript\n\n",
        encoding="utf-8",
    )
    return path


def append_turn(path: Path, speaker: str, text: str) -> None:
    """Append one turn, immediately.

    Appended rather than buffered because a twenty-minute session that dies on
    turn eighteen and loses everything is the one unrecoverable failure here.
    The candidate's time cannot be replayed.
    """
    label = {"interviewer": "Interviewer", "candidate": "Candidate"}.get(
        speaker, speaker
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"**{label}:** {text.strip()}\n\n")
