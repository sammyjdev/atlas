"""Where ATLAS keeps state. One environment variable, no file format."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HOME = "~/.atlas"


def atlas_home() -> Path:
    return Path(os.environ.get("ATLAS_HOME", DEFAULT_HOME)).expanduser()


def module_home(name: str) -> Path:
    return atlas_home() / name


def atlas_vault() -> Path:
    """Private checkout root. No default and no cwd fallback."""
    raw = os.environ.get("ATLAS_VAULT")
    if not raw:
        raise RuntimeError("ATLAS_VAULT is not set")
    return Path(raw).expanduser()
