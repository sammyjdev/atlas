"""Read the Merit ledger. One SQLite file; Alfa does not create applications."""

import contextlib
import os
from pathlib import Path

from atlas_core.config import atlas_home, module_home
from atlas_merit import rank, track
from atlas_merit.profile import ProfileError, load_profile
from langgraph.checkpoint.sqlite import SqliteSaver

LABELS = {
    "found": "encontrada",
    "queued": "na fila",
    "replied": "respondida",
    "applied": "aplicada",
    "screening": "triagem",
    "interview": "entrevista",
    "offer": "oferta",
    "accepted": "aceite",
    "archived": "arquivo",
}

_ACTIVE_SQL = """
    SELECT id, title, company, status, updated_at
    FROM applications
    WHERE status NOT IN (?, ?, ?, ?) -- count matches track.TERMINAL
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
        rows = conn.execute(_ACTIVE_SQL, track.TERMINAL).fetchall()
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


def gaps(path: str, found) -> tuple[str, list[str]] | None:
    """('match', demands) from stored verdicts, else ('rank', names) from jd.md."""
    if found["session_id"]:
        with SqliteSaver.from_conn_string(path) as saver:
            saved = saver.get_tuple({"configurable": {"thread_id": found["session_id"]}})
        verdicts = saved.checkpoint["channel_values"].get("verdicts") if saved else None
        if verdicts:
            return "match", [v["demand"] for v in verdicts if v["verdict"] == "gap"]
    profile = Path(os.environ.get("MERIT_PROFILE", atlas_home() / "profile.yaml"))
    dossier = track.dossier_of(path, found["dossier_dir"])
    jd = dossier / "jd.md" if dossier else None
    if jd is None or not profile.is_file() or not jd.is_file():
        return None
    text = jd.read_text(encoding="utf-8", errors="replace")
    try:
        return "rank", rank.hit_names(load_profile(profile), text)["gap"]
    except ProfileError:
        return None


def entries(path: str, app_id: int, file: str) -> list[tuple[str, str]]:
    return [
        (stamp, body)
        for stamp, source, body in track.entries(path, app_id)
        if source == file
    ]
