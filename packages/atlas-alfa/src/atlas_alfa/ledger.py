"""Read the Merit ledger. One SQLite file; Alfa does not create applications."""

import contextlib
import os
from pathlib import Path

from atlas_core.config import module_home
from atlas_merit import track

# Product terminals that already exist as SQL statuses: recusa, saí.
# aceite and arquivo have no column. offer stays on the list.
TERMINAL = ("rejected", "withdrawn")

LABELS = {
    "found": "encontrada",
    "queued": "na fila",
    "replied": "respondida",
    "applied": "aplicada",
    "screening": "triagem",
    "interview": "entrevista",
    "offer": "oferta",
}

_ACTIVE_SQL = """
    SELECT id, title, company, status, updated_at
    FROM applications
    WHERE status NOT IN ('rejected', 'withdrawn')
    ORDER BY updated_at DESC, id
"""


def db_path() -> str:
    raw = os.environ.get("MERIT_DB")
    path = Path(raw) if raw else module_home("merit") / "merit.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def dossier_root() -> Path:
    return Path(db_path()).parent / "applications"


def active_rows(path: str) -> list[dict]:
    # ponytail: track._conn is the same private opener merit serve uses.
    with contextlib.closing(track._conn(path)) as conn:
        rows = conn.execute(_ACTIVE_SQL).fetchall()
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "company": row["company"],
            "status": row["status"],
            "label": LABELS.get(row["status"], row["status"]),
        }
        for row in rows
    ]


def row(path: str, app_id: int):
    with contextlib.closing(track._conn(path)) as conn:
        return conn.execute(track._SELECT_ROW_SQL, {"id": app_id}).fetchone()


def thread_entries(path: str, app_id: int) -> list[tuple[str, str]]:
    return [
        (stamp, body)
        for stamp, source, body in track.entries(path, app_id)
        if source == "thread"
    ]
