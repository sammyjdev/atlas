from __future__ import annotations

import re
from pathlib import Path

# Common words that carry no topical signal — excluded from keyword matching.
_STOPWORDS = {"and", "the", "of", "vs", "with", "for", "to", "in", "on", "by"}

_READABLE_SUFFIXES = (".md", ".txt")


def load_jds(jds_dir: Path) -> list[str]:
    """Read every .md/.txt file in jds_dir and return their lowercased text.

    Returns an empty list if the directory does not exist.
    """
    if not jds_dir.exists():
        return []
    texts: list[str] = []
    for path in sorted(jds_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in _READABLE_SUFFIXES:
            texts.append(path.read_text(encoding="utf-8").lower())
    return texts


def _topic_keywords(topic: str) -> set[str]:
    """Tokenize a topic into meaningful keywords (drop stopwords and short tokens)."""
    words = re.findall(r"[a-z0-9]+", topic.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def match_topics(
    jd_texts: list[str], syllabus: list[dict], min_hits: int = 2
) -> list[dict]:
    """Return syllabus items whose keywords appear (as whole words) in the JD text.

    A topic matches when at least `min_hits` of its keywords occur in the combined
    JD text, or all of its keywords if it has fewer than `min_hits`. Order of the
    returned items follows the order of `syllabus`.
    """
    if not jd_texts:
        return []
    blob = "\n".join(jd_texts)
    matched: list[dict] = []
    for item in syllabus:
        keywords = _topic_keywords(item["topic"])
        if not keywords:
            continue
        hits = sum(1 for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", blob))
        threshold = min(min_hits, len(keywords))
        if hits >= threshold:
            matched.append(item)
    return matched


def prioritize_gaps(gaps: list[dict], jd_texts: list[str]) -> list[tuple[dict, str]]:
    """Order gaps so JD-relevant topics come first, tagging each with its source.

    Returns (item, source) pairs where source is "jd" for JD-matched topics and
    "syllabus" otherwise. Relative order within each group preserves input order.
    """
    if not jd_texts:
        return [(g, "syllabus") for g in gaps]
    matched_keys = {(m["topic"], m["nicho"]) for m in match_topics(jd_texts, gaps)}
    jd_first = [(g, "jd") for g in gaps if (g["topic"], g["nicho"]) in matched_keys]
    rest = [
        (g, "syllabus") for g in gaps if (g["topic"], g["nicho"]) not in matched_keys
    ]
    return jd_first + rest


def pending_jds(
    jds_dir: Path, done: list[str], key_prefix: str = "interview"
) -> list[tuple[str, str]]:
    """Return (slug, text) for every JD with no entry yet on this track.

    The slug is the file stem, so `acme-ai-engineer.md` is tracked in state as
    `interview:acme-ai-engineer`. Both the done and the permanently-failed forms
    are skipped.

    The prefix is a parameter because pending is per track: a posting whose
    technical interview is finished is still pending for the screening call,
    which is a different conversation about the same job.
    """
    if not jds_dir.exists():
        return []
    seen = set(done)
    out: list[tuple[str, str]] = []
    for path in sorted(jds_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _READABLE_SUFFIXES:
            continue
        slug = path.stem
        key = f"{key_prefix}:{slug}"
        if key in seen or f"__failed__:{key}" in seen:
            continue
        out.append((slug, path.read_text(encoding="utf-8")))
    return out
