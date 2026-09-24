import json
import sys
import textwrap
from pathlib import Path

from atlas_sage import main
from atlas_sage.state import State


def test_refill_queue_prioritizes_jd_matches(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path))
    syllabus = tmp_path / "inputs" / "syllabus.yaml"
    syllabus.parent.mkdir()
    syllabus.write_text(textwrap.dedent("""
        java:
          - records and sealed classes
          - virtual threads (JEP 444)
    """))
    jds = tmp_path / "inputs" / "jds"
    jds.mkdir()
    (jds / "role.md").write_text("Looking for virtual threads and Loom experience")

    state = State()
    main.refill_queue(state)

    assert len(state.queue) == 2
    assert state.queue[0]["topic"] == "virtual threads (JEP 444)"
    assert state.queue[0]["source"] == "jd"
    assert state.queue[1]["source"] == "syllabus"


def test_refill_queue_no_jds_all_syllabus(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path))
    syllabus = tmp_path / "inputs" / "syllabus.yaml"
    syllabus.parent.mkdir()
    syllabus.write_text("java:\n  - virtual threads (JEP 444)\n")

    state = State()
    main.refill_queue(state)

    assert len(state.queue) == 1
    assert state.queue[0]["source"] == "syllabus"


def test_status_flag_writes_status_md(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "queue": [],
                "done": ["attention-mechanism"],
                "retries": {},
                "usage": {
                    "date": "2026-06-17",
                    "writer_calls": 0,
                    "critic_calls": 0,
                    "tavily_calls": 0,
                },
            }
        )
    )
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path))
    syllabus_file = tmp_path / "inputs" / "syllabus.yaml"
    syllabus_file.parent.mkdir()
    syllabus_file.write_text("llms:\n  - attention mechanism\n")
    status_file = tmp_path / "STATUS.md"
    monkeypatch.setattr(sys, "argv", ["sage", "--status"])

    rc = main.cli()

    assert rc == 0
    assert status_file.exists()
    text = status_file.read_text(encoding="utf-8")
    assert text.startswith("# SAGE Status")
    assert "## Coverage" in text


def test_status_path_env_override(tmp_path, monkeypatch):
    custom = tmp_path / "custom-status.md"
    monkeypatch.setenv("SAGE_STATUS", str(custom))
    assert main.status_path() == custom


def test_once_refreshes_status_md(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "queue": [],
                "done": [],
                "retries": {},
                "usage": {
                    "date": "2026-06-17",
                    "writer_calls": 0,
                    "critic_calls": 0,
                    "tavily_calls": 0,
                },
            }
        )
    )
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path))
    syllabus_file = tmp_path / "inputs" / "syllabus.yaml"
    syllabus_file.parent.mkdir()
    syllabus_file.write_text("llms:\n  - attention mechanism\n")
    status_file = tmp_path / "STATUS.md"
    monkeypatch.setattr(main, "run_once", lambda **kwargs: {"status": "idle"})
    monkeypatch.setattr(sys, "argv", ["sage", "--once"])

    rc = main.cli()

    assert rc == 0
    assert status_file.exists()
    assert "# SAGE Status" in status_file.read_text(encoding="utf-8")


def _seed_interview_inputs(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "profile.md").write_text("candidate\n")
    jds = inputs / "jds"
    jds.mkdir()
    (jds / "role.md").write_text("role\n")


def _state_file(tmp_path: Path) -> Path:
    f = tmp_path / "state.json"
    f.write_text(
        json.dumps(
            {
                "queue": [],
                "done": [],
                "retries": {},
                "failures": {},
                "usage": {
                    "date": "2026-06-17",
                    "writer_calls": 0,
                    "critic_calls": 0,
                    "tavily_calls": 0,
                },
            }
        )
    )
    return f


def test_dry_run_persists_nothing(tmp_path, monkeypatch):
    """A real call, no footprint.

    Validating a fix against the live models should not cost a __failed__ entry
    and two of the three retries a slug is allowed - the last batch burned six
    of sixteen slots that way. Dry run keeps the request real and the write
    side inert.
    """
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path))
    _seed_interview_inputs(tmp_path)
    state_file = _state_file(tmp_path)
    before = state_file.read_text()
    status_file = tmp_path / "STATUS.md"
    vault = tmp_path / "vault"
    monkeypatch.setenv("SAGE_VAULT", str(vault))

    def fake_interview(state, **kwargs):
        state.done.append("interview:whatever")  # would normally be persisted
        return {"status": "approved", "slug": "interview:whatever"}

    monkeypatch.setattr(main, "run_interview", fake_interview)
    monkeypatch.setattr(sys, "argv", ["sage", "--interview", "--dry-run"])

    rc = main.cli()

    assert rc == 0
    assert state_file.read_text() == before, "state.json must be untouched"
    assert not status_file.exists(), "STATUS.md must not be rewritten"
    assert not vault.exists(), "the real vault must not be written to"
    assert not (tmp_path / "exports" / "sage.apkg").exists()


def test_dry_run_writes_into_a_throwaway_vault(tmp_path, monkeypatch):
    """The document still gets produced, just not where anyone reads it."""
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path))
    _seed_interview_inputs(tmp_path)
    _state_file(tmp_path)
    vault = tmp_path / "vault"
    monkeypatch.setenv("SAGE_VAULT", str(vault))

    seen = {}

    def fake_interview(state, vault_root, **kwargs):
        seen["vault_root"] = vault_root
        return {"status": "approved", "slug": "interview:x"}

    monkeypatch.setattr(main, "run_interview", fake_interview)
    monkeypatch.setattr(sys, "argv", ["sage", "--interview", "--dry-run"])

    main.cli()

    assert seen["vault_root"] != vault, "must not target the configured vault"
    assert "dry" in str(seen["vault_root"]).lower()


def test_dry_run_status_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path))
    state_file = _state_file(tmp_path)
    before = state_file.read_text()
    monkeypatch.setattr(sys, "argv", ["sage", "--status", "--dry-run"])

    rc = main.cli()

    assert rc == 0
    assert state_file.read_text() == before
    assert not (tmp_path / "STATUS.md").exists()


def test_dry_run_export_only_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path))
    state_file = _state_file(tmp_path)
    before = state_file.read_text()
    monkeypatch.setattr(sys, "argv", ["sage", "--export-only", "--dry-run"])

    rc = main.cli()

    assert rc == 0
    assert state_file.read_text() == before
    assert not (tmp_path / "exports" / "sage.apkg").exists()
    assert not (tmp_path / "STATUS.md").exists()


def test_import_does_not_configure_the_root_logger(monkeypatch):
    import importlib
    import logging

    calls = []
    monkeypatch.setattr(logging, "basicConfig", lambda *args, **kwargs: calls.append(kwargs))
    importlib.reload(main)
    assert calls == []


def test_cli_configures_logging(monkeypatch, tmp_path):
    import logging

    calls = []
    monkeypatch.setattr(logging, "basicConfig", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["sage", "--status", "--dry-run"])
    main.cli()
    assert calls
