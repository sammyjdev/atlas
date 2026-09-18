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
