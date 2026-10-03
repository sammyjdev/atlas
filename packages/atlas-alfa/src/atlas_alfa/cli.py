"""`alfa` binds localhost only. merit serve stays the debug UI."""

import json
import sys

HOST_ECHO = "Tess on http://{host}:{port} (localhost only)"
USAGE = "uso: alfa [--port N] | alfa gmail-query | alfa gmail-candidatos < mensagens.json"


def _port(argv: list[str]) -> int:
    if not argv:
        return 4317
    if argv[:1] == ["--port"] and len(argv) == 2:
        try:
            return int(argv[1])
        except ValueError:
            pass
    print(USAGE, file=sys.stderr)
    raise SystemExit(2)


def _candidatos() -> None:
    from atlas_alfa import gmail, pending

    try:
        items = json.load(sys.stdin)
    except ValueError:
        items = None
    if not isinstance(items, list):
        print(USAGE, file=sys.stderr)
        raise SystemExit(2)
    found, skipped = gmail.from_mcp(items)
    try:
        added = pending.merge(found)
    except pending.PendingError:
        print(f"pendentes ilegivel: {pending.FILE}", file=sys.stderr)
        raise SystemExit(2) from None
    print(added)
    if skipped:
        print(f"ignorados: {skipped}", file=sys.stderr)


def main() -> None:
    argv = sys.argv[1:]
    if argv == ["gmail-query"]:
        from atlas_alfa import gmail

        print(gmail.QUERY)
        return
    if argv == ["gmail-candidatos"]:
        _candidatos()
        return

    import uvicorn

    from atlas_alfa.app import HOST, create_app

    assert HOST == "127.0.0.1"  # noqa: S101
    port = _port(argv)
    print(HOST_ECHO.format(host=HOST, port=port))
    uvicorn.run(create_app(), host=HOST, port=port, log_level="warning")
