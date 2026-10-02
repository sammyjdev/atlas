"""`alfa` binds localhost only. merit serve stays the debug UI."""

import sys

HOST_ECHO = "Tess on http://{host}:{port} (localhost only)"


def _port(argv: list[str]) -> int:
    if not argv:
        return 4317
    if argv[:1] == ["--port"] and len(argv) == 2:
        try:
            return int(argv[1])
        except ValueError:
            pass
    print("uso: alfa [--port N]", file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    import uvicorn

    from atlas_alfa.app import HOST, create_app

    assert HOST == "127.0.0.1"  # noqa: S101
    port = _port(sys.argv[1:])
    print(HOST_ECHO.format(host=HOST, port=port))
    uvicorn.run(create_app(), host=HOST, port=port, log_level="warning")
