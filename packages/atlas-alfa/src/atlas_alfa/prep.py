"""Read interviews `sage --interview` already wrote. No subprocess, no model call, no write."""

from pathlib import Path

import yaml
from atlas_core.config import atlas_vault

TRACKS = ("interview", "screening")
NO_VAULT = "ATLAS_VAULT ausente."


def _vault() -> Path | None:
    try:
        return atlas_vault() / "vault"
    except RuntimeError:
        return None


def _split(path: Path) -> tuple[dict, str] | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    try:
        meta = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None
    return (meta, text[end + 5 :].strip()) if isinstance(meta, dict) else None


def interviews() -> dict[str, Path] | None:
    """'track/slug' -> file, for every entry with cards. None when ATLAS_VAULT is unset."""
    vault = _vault()
    if vault is None:
        return None
    found = {}
    for track in TRACKS:
        for path in sorted((vault / track).glob("*.md")):
            parsed = _split(path)
            if parsed and parsed[0].get("cards"):
                found[f"{track}/{path.stem}"] = path
    return found


def titles(found: dict[str, Path]) -> list[tuple[str, str]]:
    return [(key, _split(path)[0].get("title") or key) for key, path in found.items()]


def render(path: Path, anki: bool) -> str:
    meta, body = _split(path)
    if not anki:
        return body
    cards = [c for c in meta["cards"] if c.get("q") and c.get("a")]
    return "\n\n".join(f"Front: {c['q'].strip()}\nBack: {c['a'].strip()}" for c in cards)
