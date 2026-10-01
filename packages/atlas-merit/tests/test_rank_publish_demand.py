from pathlib import Path

from atlas_core.contracts import DemandSignal
from typer.testing import CliRunner

from atlas_merit import cli
from atlas_merit.profile import load_profile
from atlas_merit.rank import demand_signal_from_rank, rank_dir

FIXTURE = Path(__file__).parent / "fixtures" / "profile_rank.yaml"
runner = CliRunner()


def test_demand_signal_has_skill_counts_not_posting_bodies(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    path.write_text("# Role\n\nFastAPI required.\n", encoding="utf-8")
    profile = load_profile(FIXTURE)
    rows, _ = rank_dir(profile, tmp_path)
    signal = demand_signal_from_rank(profile, tmp_path, rows)
    assert signal.postings == 1
    assert any(s.name == "FastAPI" for s in signal.skills)
    dumped = signal.model_dump_json()
    assert "FastAPI" in dumped
    assert "required" not in dumped


def test_cli_rank_publishes_demand_signal_when_vault_set(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".git").mkdir()
    monkeypatch.setenv("ATLAS_VAULT", str(vault))
    monkeypatch.setattr("atlas_merit.rank.VaultGitStore._git", lambda self, *args: None)
    postings = tmp_path / "postings"
    postings.mkdir()
    (postings / "a.md").write_text("# Role\n\nFastAPI required.\n", encoding="utf-8")
    result = runner.invoke(cli.app, ["rank", str(postings), "--profile", str(FIXTURE)])
    assert result.exit_code == 0, result.output
    files = list((vault / "exchange" / "demand").glob("*.json"))
    assert len(files) == 1
    signal = DemandSignal.model_validate_json(files[0].read_text(encoding="utf-8"))
    assert signal.postings == 1
    assert any(s.name == "FastAPI" for s in signal.skills)


def test_cli_rank_publishes_when_vault_git_is_a_file(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".git").write_text("gitdir: /tmp/fake.git\n")
    monkeypatch.setenv("ATLAS_VAULT", str(vault))
    monkeypatch.setattr("atlas_merit.rank.VaultGitStore._git", lambda self, *args: None)
    postings = tmp_path / "postings"
    postings.mkdir()
    (postings / "a.md").write_text("# Role\n\nFastAPI required.\n", encoding="utf-8")
    result = runner.invoke(cli.app, ["rank", str(postings), "--profile", str(FIXTURE)])
    assert result.exit_code == 0, result.output
    files = list((vault / "exchange" / "demand").glob("*.json"))
    assert len(files) == 1


def test_cli_rank_skips_publish_without_atlas_vault(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_VAULT", raising=False)
    (tmp_path / "a.md").write_text("# Role\n\nFastAPI required.\n", encoding="utf-8")
    result = runner.invoke(cli.app, ["rank", str(tmp_path), "--profile", str(FIXTURE)])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "exchange").exists()
