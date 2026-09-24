from __future__ import annotations

import json
import re
from dataclasses import dataclass

import yaml


class ParseError(Exception):
    pass


# How much of the offending output to quote back. The tail, not the head:
# truncation is the failure this has to distinguish, and a truncated document
# looks perfectly well-formed from the front.
EXCERPT_CHARS = 220


def _evidence(text: str) -> str:
    """Describe what actually arrived, for an error that says what was wanted.

    A batch of interviews died on writer_parse and left only the rule that
    fired - "no body section found after frontmatter" - which cannot tell a
    truncated response from a malformed one. The reason string is what reaches
    state.json, so the evidence has to travel inside it.
    """
    tail = text[-EXCERPT_CHARS:].strip()
    return f" [got {len(text)} chars, ends: ...{tail!r}]"


_CODE_FENCE_RE = re.compile(r"^```(?:markdown|md)?\s*\n(.*?)\n```\s*$", re.DOTALL)
_CITATION_RE = re.compile(r"\[\^[1-9]\d*\]")


def _strip_to_frontmatter(text: str) -> str:
    fence = _CODE_FENCE_RE.search(text.strip())
    if fence:
        text = fence.group(1).strip()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "---":
            return "\n".join(lines[i:])
    return text


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.lstrip().startswith("---"):
        raise ParseError("missing YAML frontmatter" + _evidence(text))
    after_open = text.split("---", 1)[1].lstrip("\n")
    lines = after_open.splitlines()
    yaml_lines: list[str] = []
    body_start = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            body_start = i + 1
            break
        if line.startswith("## "):
            body_start = i
            break
        yaml_lines.append(line)
    if body_start is None:
        raise ParseError("no body section found after frontmatter" + _evidence(text))
    yaml_block = "\n".join(yaml_lines)
    body = "\n".join(lines[body_start:])
    return yaml_block, body


def parse_writer_output(text: str) -> dict:
    text = _strip_to_frontmatter(text)
    yaml_block, body = _split_frontmatter(text)
    try:
        meta = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError as e:
        raise ParseError(f"invalid YAML: {e}" + _evidence(yaml_block))

    if "## Summary" not in body or "## Interview Q&A" not in body:
        raise ParseError(
            "missing required sections (## Summary / ## Interview Q&A)"
            + _evidence(body)
        )

    summary_part, _, qa_part = body.partition("## Interview Q&A")
    summary = summary_part.replace("## Summary", "", 1).strip()
    qa = qa_part.strip()

    if not summary:
        raise ParseError("empty summary")
    if not qa:
        raise ParseError("empty Q&A")

    if not _CITATION_RE.search(summary):
        raise ParseError("no inline citations in summary")
    if not _CITATION_RE.search(qa):
        raise ParseError("no inline citations in Q&A")

    return {
        "sources_cited": meta.get("sources_cited", []) or [],
        "cards": meta.get("cards", []) or [],
        "summary": summary,
        "qa": qa,
    }


@dataclass
class CriticResult:
    approved: bool
    confidence: str
    issues: list[dict]

    def decision_accepts(self) -> bool:
        if not self.approved:
            return False
        if self.confidence == "low":
            return False
        return True


def parse_critic_output(text: str) -> CriticResult:
    idx = text.find("{")
    if idx == -1:
        raise ParseError("no JSON object found in critic output" + _evidence(text))
    try:
        data, _ = json.JSONDecoder().raw_decode(text[idx:])
    except json.JSONDecodeError as e:
        raise ParseError(f"invalid critic JSON: {e}" + _evidence(text))
    return CriticResult(
        approved=bool(data.get("approved", False)),
        confidence=str(data.get("confidence", "low")),
        issues=list(data.get("issues", []) or []),
    )


MIN_RUBRIC_POINTS = 3


def render_qa(cards: list[dict]) -> str:
    """Build the readable Q&A section from the cards.

    The writer used to produce this itself, which meant writing every question
    twice: once as YAML and once as prose, identical text both times. Rendering
    it here costs nothing and halves what the model has to emit.
    """
    blocks = []
    for card in cards:
        question = (card.get("q") or "").strip()
        rubric = (card.get("a") or "").strip()
        blocks.append(f"**Q: {question}**\n\nA strong answer must contain:\n\n{rubric}")
    return "\n\n".join(blocks)


def parse_interview_output(text: str) -> dict:
    """Parse the adversarial interview document.

    Same frontmatter/sections shape as parse_writer_output, minus the citation
    requirement: this mode has no web sources to cite, its inputs are the profile
    and the posting. In exchange it enforces the rubric, which is the thing that
    makes a question gradeable.
    """
    text = _strip_to_frontmatter(text)
    yaml_block, body = _split_frontmatter(text)
    try:
        meta = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError as e:
        raise ParseError(f"invalid YAML: {e}" + _evidence(yaml_block))

    if "## Summary" not in body:
        raise ParseError("missing required section (## Summary)" + _evidence(body))

    # No `## Interview Q&A` is required here, unlike the study track. It used to
    # be, and it was the cards written a second time in prose: the same question
    # verbatim, the same rubric reworded. That doubled a 4000-token document and
    # was the dominant cause of truncation - six of eleven technical failures in
    # one run cut off mid-rubric, with the budget already raised once. The
    # section is rendered from the cards at write time, so the file a reader
    # opens is unchanged.
    summary_part, _, _ = body.partition("## Interview Q&A")
    summary = summary_part.replace("## Summary", "", 1).strip()

    if not summary:
        raise ParseError("empty summary" + _evidence(body))

    cards = meta.get("cards") or []
    if not cards:
        raise ParseError("no cards produced" + _evidence(body))

    for i, card in enumerate(cards, 1):
        question = (card.get("q") or "").strip()
        rubric = (card.get("a") or "").strip()
        if not question:
            raise ParseError(f"card #{i}: empty question" + _evidence(yaml_block))
        points = [ln for ln in rubric.splitlines() if ln.strip().startswith("-")]
        if len(points) < MIN_RUBRIC_POINTS:
            raise ParseError(
                f"card #{i}: rubric has {len(points)} point(s), "
                f"needs at least {MIN_RUBRIC_POINTS}" + _evidence(rubric)
            )

    return {
        "vaga": meta.get("vaga", ""),
        "cards": cards,
        "summary": summary,
        "qa": render_qa(cards),
        "sources_cited": [],
    }
