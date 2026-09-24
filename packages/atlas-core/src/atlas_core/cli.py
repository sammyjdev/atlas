"""Facade: `atlas <module> ...` loads `atlas.modules` entry points."""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from importlib.metadata import entry_points

Module = Callable[[], object]


def _installed_modules() -> dict[str, Module]:
    found = entry_points(group="atlas.modules")
    return {ep.name: ep.load() for ep in found}


def _invoke(name: str, target: Module, rest: list[str]) -> int:
    previous = sys.argv
    sys.argv = [name, *rest]
    try:
        try:
            result = target()
        except SystemExit as exc:
            code = exc.code
            if code is None or code == 0:
                return 0
            if isinstance(code, int):
                return code
            return 1
    finally:
        sys.argv = previous
    if isinstance(result, int):
        return result
    return 0


def main(argv: list[str] | None = None, modules: Mapping[str, Module] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    available = dict(modules) if modules is not None else _installed_modules()
    if not args or args[0] in {"-h", "--help"}:
        names = "\n".join(f"  {name}" for name in sorted(available))
        print(f"usage: atlas <module> [args]\n\nmodules:\n{names}")
        return 0
    name, rest = args[0], args[1:]
    target = available.get(name)
    if target is None:
        print(f"unknown module: {name}", file=sys.stderr)
        return 2
    return _invoke(name, target, rest)
