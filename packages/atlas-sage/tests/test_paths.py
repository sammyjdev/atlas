import sys
from pathlib import Path

import pytest

from atlas_sage import main


def test_state_and_inputs_follow_atlas_vault(monkeypatch, tmp_path):
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path))
    assert main.state_path() == tmp_path / "state.json"
    assert main.syllabus_path() == tmp_path / "inputs" / "syllabus.yaml"
    assert main.jds_path() == tmp_path / "inputs" / "jds"
    assert main.profile_path() == tmp_path / "inputs" / "profile.md"


def test_vault_apkg_and_status_default_under_atlas_vault(monkeypatch, tmp_path):
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path))
    monkeypatch.delenv("SAGE_VAULT", raising=False)
    monkeypatch.delenv("SAGE_APKG", raising=False)
    monkeypatch.delenv("SAGE_STATUS", raising=False)
    assert main.vault_root() == tmp_path / "vault"
    assert main.apkg_path() == tmp_path / "exports" / "sage.apkg"
    assert main.status_path() == tmp_path / "STATUS.md"


def test_sage_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path))
    monkeypatch.setenv("SAGE_VAULT", "~/custom-vault")
    monkeypatch.setenv("SAGE_APKG", str(tmp_path / "deck.apkg"))
    monkeypatch.setenv("SAGE_STATUS", str(tmp_path / "note.md"))
    assert main.vault_root() == Path.home() / "custom-vault"
    assert main.apkg_path() == tmp_path / "deck.apkg"
    assert main.status_path() == tmp_path / "note.md"


def test_override_does_not_satisfy_missing_atlas_vault(monkeypatch, tmp_path):
    monkeypatch.delenv("ATLAS_VAULT", raising=False)
    monkeypatch.setenv("SAGE_STATUS", str(tmp_path / "note.md"))
    with pytest.raises(RuntimeError, match="ATLAS_VAULT"):
        main.state_path()


def test_cli_missing_atlas_vault_is_an_error(monkeypatch):
    monkeypatch.delenv("ATLAS_VAULT", raising=False)
    monkeypatch.setattr(sys, "argv", ["sage", "--status"])
    assert main.cli() == 1
