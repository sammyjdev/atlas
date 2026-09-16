"""Append-only file exchange between modules.

One immutable JSON file per item, named by a sortable id. Each consumer keeps
its own cursor (the last id it processed). No module edits another module's
files. Idempotent by construction: re-reading from the same cursor yields the
same items.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from pydantic import BaseModel

_last_ns = 0


_last_ns = 0


def new_id() -> str:
    # ponytail: stdlib sortable id (ns timestamp + uuid4); swap for python-ulid
    # only if an external tool needs the ULID encoding. The clamp keeps ids
    # strictly increasing inside one process even when the clock does not tick.
    global _last_ns
    now = max(time.time_ns(), _last_ns + 1)
    _last_ns = now
    return f"{now:020d}-{uuid.uuid4().hex}"


class LocalExchangeStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def publish(self, channel: str, item: BaseModel) -> str:
        item_id = new_id()
        folder = self.root / channel
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / f"{item_id}.json").open("x") as handle:
            handle.write(item.model_dump_json(indent=2))
        return item_id

    def read(self, channel: str, since: str | None = None) -> list[tuple[str, dict]]:
        folder = self.root / channel
        if not folder.is_dir():
            return []
        items = []
        for path in sorted(folder.glob("*.json")):
            item_id = path.stem
            if since is not None and item_id <= since:
                continue
            items.append((item_id, json.loads(path.read_text())))
        return items


class Cursor:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self) -> str | None:
        return self.path.read_text().strip() if self.path.exists() else None

    def set(self, value: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(value + "\n")
