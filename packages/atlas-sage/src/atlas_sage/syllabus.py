from __future__ import annotations

from pathlib import Path

import yaml

from .state import slug


def load_syllabus(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text()) or {}
    items = []
    for nicho, topics in data.items():
        for topic in topics:
            items.append({"topic": topic, "nicho": nicho})
    return items


def find_gaps(syllabus: list[dict], done: list[str], queued: list[dict]) -> list[dict]:
    done_slugs = {d.removeprefix("__failed__:") for d in done}
    queued_slugs = {slug(q["topic"]) for q in queued}
    out = []
    for item in syllabus:
        s = slug(item["topic"])
        if s in done_slugs or s in queued_slugs:
            continue
        out.append(item)
    return out
