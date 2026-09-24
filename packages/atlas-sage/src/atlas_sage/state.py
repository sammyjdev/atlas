from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class State:
    queue: list[dict] = field(default_factory=list)
    done: list[str] = field(default_factory=list)
    retries: dict[str, int] = field(default_factory=dict)
    failures: dict[str, dict] = field(default_factory=dict)
    usage: dict = field(
        default_factory=lambda: {
            "date": date.today().isoformat(),
            "writer_calls": 0,
            "critic_calls": 0,
            "tavily_calls": 0,
        }
    )


def load(path: Path) -> State:
    if not path.exists():
        return State()
    data = json.loads(path.read_text())
    return State(
        queue=data.get("queue", []),
        done=data.get("done", []),
        retries=data.get("retries", {}),
        failures=data.get("failures", {}),
        usage=data.get("usage", State().usage),
    )


def save(path: Path, state: State) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(state), indent=2, ensure_ascii=False))
    os.replace(tmp, path)


MAX_RETRIES = 2


def slug(topic: str) -> str:
    import re

    s = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    return s


def _drop_from_queue(state: State, s: str) -> None:
    state.queue = [it for it in state.queue if slug(it["topic"]) != s]


def record_done(state: State, slug: str) -> None:
    _drop_from_queue(state, slug)
    if slug not in state.done:
        state.done.append(slug)
    state.retries.pop(slug, None)
    state.failures.pop(slug, None)


def _mark_failed(state: State, slug: str, reason: str | None) -> None:
    _drop_from_queue(state, slug)
    failed = f"__failed__:{slug}"
    if failed not in state.done:
        state.done.append(failed)
    state.retries.pop(slug, None)
    if reason is not None:
        state.failures[slug] = {"reason": reason, "date": date.today().isoformat()}


def record_failed(state: State, slug: str, reason: str) -> None:
    """Permanently fail a slug outright (e.g. insufficient sources), with reason."""
    _mark_failed(state, slug, reason)


def record_retry(state: State, slug: str, reason: str | None = None) -> None:
    current = state.retries.get(slug, 0) + 1
    if current >= MAX_RETRIES:
        _mark_failed(state, slug, reason)
    else:
        state.retries[slug] = current
