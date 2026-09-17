# tests/test_cli_enrich.py
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from atlas_merit import cli, fetch, queue

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "linkedin"
LIVE_HTML = (FIXTURES / "job_live.html").read_text(encoding="utf-8")
EXPIRED_HTML = (FIXTURES / "job_expired.html").read_text(encoding="utf-8")


def _recent(days_ago: int = 1) -> str:
    return (datetime.now(UTC).date() - timedelta(days=days_ago)).isoformat()


def _entry(job: str, days_ago: int = 1) -> queue.Entry:
    return queue.Entry(
        title="AI Engineer - Agents with Vertex AI",
        company="Globant - Brazil (Remote)",
        url=f"https://www.linkedin.com/jobs/view/{job}/",
        alert_date=_recent(days_ago),
    )


def _serving(html_by_job: dict[str, str | None]):
    def _fetch(job, *_args, **_kwargs):
        return html_by_job[job]

    return _fetch


def test_enrich_writes_a_rankable_posting_file(tmp_path, monkeypatch):
    queue_path = tmp_path / "queue.json"
    out_dir = tmp_path / "postings"
    queue.append_entries([_entry("111")], queue_path)
    monkeypatch.setattr(cli, "fetch_job", _serving({"111": LIVE_HTML}))
    monkeypatch.setattr(fetch, "RETRY_SLEEP", 0)

    result = runner.invoke(
        cli.app,
        ["enrich", "--days", "15", "--queue-path", str(queue_path), "--out", str(out_dir)],
    )

    assert result.exit_code == 0
    written = list(out_dir.glob("*.md"))
    assert len(written) == 1
    body = written[0].read_text(encoding="utf-8")
    assert "Vertex AI" in body
    assert "subject: AI Engineer - Agents with Vertex AI" in body


def test_enrich_drops_a_closed_posting_from_the_queue(tmp_path, monkeypatch):
    queue_path = tmp_path / "queue.json"
    out_dir = tmp_path / "postings"
    queue.append_entries([_entry("111"), _entry("222")], queue_path)
    monkeypatch.setattr(cli, "fetch_job", _serving({"111": EXPIRED_HTML, "222": LIVE_HTML}))
    monkeypatch.setattr(cli, "ENRICH_PAUSE", 0)

    result = runner.invoke(
        cli.app,
        ["enrich", "--days", "15", "--queue-path", str(queue_path), "--out", str(out_dir)],
    )

    assert result.exit_code == 0
    assert [e.url for e in queue.load_entries(queue_path)] == [
        "https://www.linkedin.com/jobs/view/222/"
    ]
    assert [p.name for p in out_dir.glob("*.md")] == [f"{_recent()}-222.md"]


def test_enrich_drops_a_deleted_posting_and_keeps_going(tmp_path, monkeypatch):
    queue_path = tmp_path / "queue.json"
    out_dir = tmp_path / "postings"
    queue.append_entries([_entry("111"), _entry("222")], queue_path)
    monkeypatch.setattr(cli, "fetch_job", _serving({"111": None, "222": LIVE_HTML}))
    monkeypatch.setattr(cli, "ENRICH_PAUSE", 0)

    runner.invoke(
        cli.app,
        ["enrich", "--days", "15", "--queue-path", str(queue_path), "--out", str(out_dir)],
    )

    assert len(queue.load_entries(queue_path)) == 1
    assert len(list(out_dir.glob("*.md"))) == 1


def test_enrich_is_idempotent_and_respects_the_day_window(tmp_path, monkeypatch):
    queue_path = tmp_path / "queue.json"
    out_dir = tmp_path / "postings"
    queue.append_entries([_entry("111", days_ago=1), _entry("222", days_ago=40)], queue_path)
    calls: list[str] = []

    def _counting(job, *_args, **_kwargs):
        calls.append(job)
        return LIVE_HTML

    monkeypatch.setattr(cli, "fetch_job", _counting)
    monkeypatch.setattr(cli, "ENRICH_PAUSE", 0)
    args = ["enrich", "--days", "15", "--queue-path", str(queue_path), "--out", str(out_dir)]

    runner.invoke(cli.app, args)
    runner.invoke(cli.app, args)

    assert calls == ["111"]  # 222 is outside the window; neither job is fetched twice
    assert len(list(out_dir.glob("*.md"))) == 1
