from pathlib import Path

from atlas_core import config


def test_atlas_home_defaults_under_the_user_home(monkeypatch):
    monkeypatch.delenv("ATLAS_HOME", raising=False)
    assert config.atlas_home() == Path.home() / ".atlas"


def test_atlas_home_follows_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "state"))
    assert config.atlas_home() == tmp_path / "state"


def test_module_home_is_a_subdirectory(monkeypatch, tmp_path):
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path))
    assert config.module_home("merit") == tmp_path / "merit"


def test_module_home_expands_a_tilde(monkeypatch):
    monkeypatch.setenv("ATLAS_HOME", "~/somewhere")
    assert config.module_home("merit") == Path.home() / "somewhere" / "merit"


def test_atlas_vault_reads_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path / "checkout"))
    assert config.atlas_vault() == tmp_path / "checkout"


def test_atlas_vault_expands_a_tilde(monkeypatch):
    monkeypatch.setenv("ATLAS_VAULT", "~/sage")
    assert config.atlas_vault() == Path.home() / "sage"


def test_atlas_vault_missing_is_an_error(monkeypatch):
    monkeypatch.delenv("ATLAS_VAULT", raising=False)
    try:
        config.atlas_vault()
    except RuntimeError as exc:
        assert "ATLAS_VAULT" in str(exc)
    else:
        raise AssertionError("missing ATLAS_VAULT must fail")
