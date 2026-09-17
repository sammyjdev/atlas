"""CLI shell: IO, sessions, and printing. No LLM logic beyond wiring builders."""

import http.client
import os
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import typer
from atlas_core.config import atlas_home, module_home
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from atlas_merit import mail as mail_module
from atlas_merit import queue, track
from atlas_merit.fetch import fetch_job, fetch_posting, job_id, parse_job
from atlas_merit.graph.build import build_graph
from atlas_merit.mail import (
    INBOX_DIR,
    MailError,
    connect,
    fetch_messages,
    ingest_alerts,
    ingest_messages,
)
from atlas_merit.models import build_extractor, build_judge, build_writer
from atlas_merit.profile import load_profile, profile_hash, strong_terms
from atlas_merit.rank import DEFAULT_TOP, rank_dir
from atlas_merit.rank import render as render_rank

app = typer.Typer(add_completion=False)
track_app = typer.Typer(add_completion=False)
app.add_typer(track_app, name="track")

def _db_path() -> str:
    path = Path(os.environ.get("MERIT_DB", module_home("merit") / "merit.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _profile_path(profile: str | None) -> Path:
    return Path(profile) if profile else atlas_home() / "profile.yaml"


def _dossier_root() -> Path:
    return Path(_db_path()).parent / "applications"


def _read_posting(posting: str) -> tuple[str, dict]:
    if posting == "-":
        return sys.stdin.read(), {"source": "stdin"}
    if posting.startswith(("http://", "https://")):
        return fetch_posting(posting), {"source": posting}
    return Path(posting).read_text(encoding="utf-8"), {"source": posting}


def _graph(profile_path: str, saver: SqliteSaver):
    profile = load_profile(profile_path)
    return build_graph(profile, build_extractor(), build_judge(), build_writer(), saver)


@app.command()
def match(
    posting: str,
    profile: str | None = typer.Option(None, "--profile"),
    session_id: str | None = typer.Option(None, "--session-id"),
):
    text, meta = _read_posting(posting)
    sid = session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": sid}}
    with SqliteSaver.from_conn_string(_db_path()) as saver:
        profile_path = _profile_path(profile)
        graph = _graph(profile_path, saver)
        graph.invoke(
            {"posting_text": text, "posting_meta": meta, "profile_hash": profile_hash(profile_path)},
            config,
        )
        report_md = graph.get_state(config).values["report_md"]
    typer.echo(report_md)
    typer.echo(f"\nSession: {sid}")
    typer.echo(f"Resume with: merit resume {sid} --approve | --reject")


@app.command()
def resume(
    session_id: str,
    approve: bool = typer.Option(False, "--approve"),
    reject: bool = typer.Option(False, "--reject"),
    profile: str | None = typer.Option(None, "--profile"),
):
    if approve == reject:
        typer.echo("pass exactly one of --approve / --reject")
        raise typer.Exit(1)
    config = {"configurable": {"thread_id": session_id}}
    with SqliteSaver.from_conn_string(_db_path()) as saver:
        profile_path = _profile_path(profile)
        graph = _graph(profile_path, saver)
        stored = graph.get_state(config).values.get("profile_hash")
        if stored and stored != profile_hash(profile_path):
            typer.echo("profile changed since report; re-run merit match")
            raise typer.Exit(2)
        result = graph.invoke(Command(resume=approve), config)
    if approve:
        typer.echo(result["narrative_md"])
    else:
        typer.echo("Rejected; session closed.")


@app.command()
def rank(
    directory: str,
    profile: str | None = typer.Option(None, "--profile"),
    top: int = typer.Option(DEFAULT_TOP, "--top"),
):
    posting_dir = Path(directory)
    if not posting_dir.is_dir():
        typer.echo(f"not a directory: {directory}", err=True)
        raise typer.Exit(1)
    prof = load_profile(_profile_path(profile))
    rows, skipped = rank_dir(prof, posting_dir)
    typer.echo(render_rank(rows, skipped, top))


@app.command("ingest-mail")
def ingest_mail(
    out_dir: str = typer.Option(str(INBOX_DIR), "--out-dir"),
    queue_path: str = typer.Option(str(queue.QUEUE_PATH), "--queue-path"),
    full: bool = typer.Option(False, "--full"),
    mailbox: list[str] = typer.Option(  # noqa: B008 - typer reads defaults from the call
        [], "--mailbox", help="Gmail label; repeatable with --install-agent"
    ),
    install_agent: bool = typer.Option(False, "--install-agent"),
    uninstall_agent: bool = typer.Option(False, "--uninstall-agent"),
    interval: int = typer.Option(3600, "--interval", help="Sync agent period in seconds"),
):
    if install_agent and uninstall_agent:
        typer.echo("pass exactly one of --install-agent / --uninstall-agent")
        raise typer.Exit(1)

    if install_agent:
        from atlas_merit.serve import agent as launch_agent

        written = launch_agent.install_sync_agent(
            Path.home(),
            python=sys.executable,
            workdir=Path.cwd(),
            interval=interval,
            mailboxes=tuple(mailbox),
        )
        typer.echo(str(written))
        typer.echo(f"launchctl load {written}")
        return

    if uninstall_agent:
        from atlas_merit.serve import agent as launch_agent

        if launch_agent.uninstall_sync_agent(Path.home()):
            typer.echo("Sync LaunchAgent removed")
        else:
            typer.echo("No sync LaunchAgent installed")
        return

    if len(mailbox) > 1:
        typer.echo("one --mailbox per run (multiple only with --install-agent)")
        raise typer.Exit(1)
    if mailbox:
        os.environ["MERIT_IMAP_MAILBOX"] = mailbox[0]

    try:
        conn = connect()
    except MailError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None

    active_mailbox = os.environ.get("MERIT_IMAP_MAILBOX", mail_module.DEFAULT_MAILBOX)
    cursor_path = Path(out_dir) / mail_module.cursor_name(active_mailbox)
    if full:
        cursor_path.unlink(missing_ok=True)
    conn.merit_cursor = True
    conn.merit_cursor_path = cursor_path

    try:
        raws = fetch_messages(conn)
    except MailError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None
    finally:
        conn.logout()

    # Replies inside already-tracked LinkedIn threads register as contact on
    # the application's dossier instead of becoming new vagas.
    by_thread = track.threads(_db_path())
    events, raws = mail_module.match_conversations(raws, set(by_thread), Path(out_dir))
    for event in events:
        track.log(
            _db_path(),
            by_thread[event.thread],
            f"[contato recebido - email] {event.subject} ({event.date})\n\n{event.body}",
            file="thread",
            dossier_root=_dossier_root(),
        )
        mail_module.mark_seen(Path(out_dir), event.key)
    if events:
        typer.echo(f"contatos registrados {len(events)}", err=True)

    ingested, skipped = ingest_messages(raws, Path(out_dir))
    queued, alert_skipped = ingest_alerts(raws, Path(queue_path))
    for item in ingested:
        typer.echo(str(item.path))
        typer.echo(f"  merit match {item.path}")
    for reason in skipped:
        typer.echo(reason, err=True)
    for reason in alert_skipped:
        typer.echo(reason, err=True)
    typer.echo(f"ingested {len(ingested)}, skipped {len(skipped)}", err=True)
    typer.echo(f"queued {len(queued)}", err=True)
    typer.echo("  merit queue", err=True)


@app.command("queue")
def queue_cmd(
    queue_path: str = typer.Option(str(queue.QUEUE_PATH), "--queue-path"),
    all_: bool = typer.Option(False, "--all"),
    profile: str | None = typer.Option(None, "--profile"),
    prune_days: int = typer.Option(0, "--prune-days", help="Drop entries older than N days"),
):
    if prune_days:
        removed = queue.prune(Path(queue_path), days=prune_days)
        typer.echo(f"pruned {removed} entries older than {prune_days} days")
        return
    entries = queue.load_entries(Path(queue_path))
    if not entries:
        typer.echo("No queued postings yet. Run `merit ingest-mail` to check for job alerts.")
        return
    terms = strong_terms(load_profile(_profile_path(profile)))
    hot = [e for e in entries if queue.is_hot(e.title, terms)]
    cold = [e for e in entries if not queue.is_hot(e.title, terms)]

    for e in hot:
        typer.echo(f"[hot] {e.title} - {e.company or 'unknown company'}")
        typer.echo(f"  {e.url}")
    if all_:
        for e in cold:
            typer.echo(f"[cold] {e.title} - {e.company or 'unknown company'}")
            typer.echo(f"  {e.url}")

    typer.echo("\nFull match requires pasting the description: merit match -")


@track_app.command("backfill-threads")
def track_backfill_threads():
    filled = 0
    for app_id, source in track.sources_without_thread(_db_path()).items():
        path = Path(source)
        if not path.is_file():
            continue
        tid = mail_module.thread_id(path.read_text(encoding="utf-8", errors="replace"))
        if tid:
            track.set_thread_id(_db_path(), app_id, tid)
            filled += 1
    typer.echo(f"thread_id preenchido em {filled} candidaturas")


@track_app.command("add")
def track_add(
    source: str,
    title: str | None = typer.Option(None, "--title"),
    company: str | None = typer.Option(None, "--company"),
    status: str = typer.Option("found", "--status"),
    note: str | None = typer.Option(None, "--note"),
    session: str | None = typer.Option(None, "--session"),
    create_dir: bool = typer.Option(False, "--dir"),
):
    try:
        app_id = track.add(
            _db_path(),
            source,
            title=title,
            company=company,
            status=status,
            note=note,
            session_id=session,
            dossier_root=_dossier_root() if create_dir else None,
        )
    except track.TrackError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None
    typer.echo(f"added {app_id}")


@track_app.command("set")
def track_set(
    app_id: int,
    status: str,
    note: str | None = typer.Option(None, "--note"),
):
    try:
        track.set_status(_db_path(), app_id, status, note=note)
    except track.TrackError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None
    typer.echo(f"{app_id} -> {status}")


@track_app.command("list")
def track_list(status: str | None = typer.Option(None, "--status")):
    try:
        typer.echo(track.list_markdown(_db_path(), status=status))
    except track.TrackError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None


@track_app.command("log")
def track_log(
    app_id: int,
    text: str = typer.Argument("-"),
    file: str = typer.Option("thread", "--file"),
):
    body = sys.stdin.read() if text == "-" else text
    try:
        track.log(_db_path(), app_id, body, file=file, dossier_root=_dossier_root())
    except track.TrackError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None
    typer.echo(f"logged to {file} for {app_id}")


@app.command("serve")
def serve(
    port: int = typer.Option(4321, "--port"),
    install_agent: bool = typer.Option(False, "--install-agent"),
    uninstall_agent: bool = typer.Option(False, "--uninstall-agent"),
):
    if install_agent and uninstall_agent:
        typer.echo("pass exactly one of --install-agent / --uninstall-agent")
        raise typer.Exit(1)

    if install_agent:
        from atlas_merit.serve import agent as launch_agent

        binary = launch_agent.resolve_binary()
        written = launch_agent.install_agent(Path.home(), binary, port)
        typer.echo(str(written))
        typer.echo(f"launchctl load {written}")
        return

    if uninstall_agent:
        from atlas_merit.serve import agent as launch_agent

        if launch_agent.uninstall_agent(Path.home()):
            typer.echo("LaunchAgent removed")
        else:
            typer.echo("No LaunchAgent installed")
        return

    import uvicorn

    from atlas_merit.serve.app import HOST, create_app

    assert HOST == "127.0.0.1"  # noqa: S101
    typer.echo(f"MERIT serve on http://{HOST}:{port} (localhost only)")
    uvicorn.run(create_app(), host=HOST, port=port, log_level="warning")


@track_app.command("show")
def track_show(app_id: int):
    try:
        typer.echo(track.show_markdown(_db_path(), app_id))
    except track.TrackError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None


POSTINGS_DIR = "corpus/postings"
ENRICH_PAUSE = 0.8


def _posting_markdown(entry: queue.Entry, posting) -> str:
    """Frontmatter shaped for `merit rank`: it reads `subject:` for the title
    and parses `date:` as RFC 2822, so alert_date is emitted in that format
    rather than ISO."""
    sent = datetime.fromisoformat(entry.alert_date).replace(tzinfo=UTC)
    criteria = "".join(f"{k.lower().replace(' ', '-')}: {v}\n" for k, v in posting.criteria.items())
    return (
        "---\n"
        f"subject: {entry.title}\n"
        f"company: {entry.company}\n"
        f"url: {entry.url}\n"
        f"date: {format_datetime(sent)}\n"
        f"{criteria}"
        "---\n\n"
        f"{posting.description}\n"
    )


@app.command()
def enrich(
    days: int = typer.Option(15, "--days"),
    queue_path: str = typer.Option(str(queue.QUEUE_PATH), "--queue-path"),
    out: str = typer.Option(POSTINGS_DIR, "--out"),
):
    """Fetch the real description for recent queue entries so `merit rank` can
    score them. Closed and deleted postings are dropped from the queue instead
    of being written - evidence of death, never a guess from the date."""
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cutoff = (datetime.now(UTC).date() - timedelta(days=days)).isoformat()
    entries = [e for e in queue.load_entries(Path(queue_path)) if e.alert_date >= cutoff]

    written = skipped = dropped = 0
    for entry in entries:
        job = job_id(entry.url)
        if job is None:
            continue
        path = out_dir / f"{entry.alert_date}-{job}.md"
        if path.exists():
            skipped += 1
            continue
        try:
            html = fetch_job(job)
        # Everything fetch_job can raise, named rather than blind: HTTPError and
        # socket timeouts are OSError, a truncated read is an HTTPException, and
        # an over-large response is a ValueError. One bad posting never aborts
        # the batch.
        except (OSError, http.client.HTTPException, ValueError) as exc:
            typer.echo(f"failed {entry.url}: {exc}", err=True)
            time.sleep(ENRICH_PAUSE)
            continue
        posting = parse_job(html) if html is not None else None
        if posting is None or posting.expired:
            queue.discard(Path(queue_path), entry.url)
            dropped += 1
        elif not posting.description.strip():
            typer.echo(f"no description parsed: {entry.url}", err=True)
        else:
            tmp_path = path.with_name(path.name + ".tmp")
            tmp_path.write_text(_posting_markdown(entry, posting), encoding="utf-8")
            tmp_path.chmod(0o600)
            tmp_path.replace(path)
            written += 1
        time.sleep(ENRICH_PAUSE)

    typer.echo(
        f"enriched {written}, already had {skipped}, dropped {dropped} closed/deleted", err=True
    )
    typer.echo(f"  merit rank {out}", err=True)
