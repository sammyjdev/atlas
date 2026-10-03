"""Pending Gmail items: one JSON file beside merit.db, every write under flock."""

import contextlib
import fcntl
import json
import os
from pathlib import Path

from atlas_alfa import gmail, ledger

FILE = "gmail-pendentes.json"
UNREADABLE = "Arquivo de pendentes ilegivel."


class PendingError(Exception):
    pass


def _path() -> Path:
    return Path(ledger.db_path()).parent / FILE


def _read(path: Path) -> dict:
    if not path.exists():
        return {"pending": [], "seen": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PendingError(UNREADABLE) from exc
    ok = (
        isinstance(data, dict)
        and isinstance(data.get("pending"), list)
        and isinstance(data.get("seen"), list)
        and all(isinstance(item, dict) for item in data["pending"])
    )
    if not ok:
        raise PendingError(UNREADABLE)
    return data


def load() -> list[dict]:
    return _read(_path())["pending"]


def ordered(items: list[dict]) -> list[dict]:
    """Important first, then tipo order, then newest."""
    rank = list(gmail.TYPES)
    newest = sorted(items, key=lambda item: item["data"], reverse=True)
    return sorted(newest, key=lambda item: (not item["importante"], rank.index(item["tipo"])))


@contextlib.contextmanager
def _locked():
    """Yield the data; write it back only if the body did not raise."""
    path = _path()
    # The open mode only applies on creation; fchmod covers leftover files.
    lock = os.open(f"{path}.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(lock, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = _read(path)
        yield data
        tmp = path.with_name(f"{path.name}.tmp")
        fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    finally:
        os.close(lock)


def merge(items: list[dict]) -> int:
    """Add new keys, refresh a known key when the copy is newer. Returns added count."""
    added = 0
    with _locked() as data:
        by_key = {gmail.key(item): n for n, item in enumerate(data["pending"])}
        for item in items:
            n = by_key.get(gmail.key(item))
            if n is None:
                by_key[gmail.key(item)] = len(data["pending"])
                data["pending"].append(item)
                added += 1
            elif item["data"] > data["pending"][n]["data"]:
                data["pending"][n] = item
    return added
