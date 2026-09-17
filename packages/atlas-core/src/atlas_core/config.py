"""Where ATLAS keeps state. One environment variable, no file format."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HOME = "~/.atlas"


def atlas_home() -> Path:
    return Path(os.environ.get("ATLAS_HOME", DEFAULT_HOME)).expanduser()


def module_home(name: str) -> Path:
    return atlas_home() / name
