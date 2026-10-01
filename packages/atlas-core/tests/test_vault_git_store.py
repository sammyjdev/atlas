from datetime import date
from pathlib import Path

from atlas_core.contracts import DemandSignal, SkillDemand
from atlas_core.exchange import Cursor, ExchangeStore, LocalExchangeStore, VaultGitStore


def _signal(n: int) -> DemandSignal:
    return DemandSignal(
        id=f"sig-{n}",
        window_start=date(2026, 9, 1),
        window_end=date(2026, 9, 15),
        postings=n,
        skills=[SkillDemand(name="rag", count=n, share=1.0)],
    )


def test_local_and_vault_are_exchange_stores(tmp_path: Path) -> None:
    assert isinstance(LocalExchangeStore(tmp_path / "local"), ExchangeStore)
    assert isinstance(VaultGitStore(tmp_path / "vault"), ExchangeStore)


def test_publish_advances_cursor_then_reread_is_empty(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    recorded: list[tuple[str, ...]] = []

    def fake_git(self, *args: str) -> None:
        recorded.append(args)

    monkeypatch.setattr(VaultGitStore, "_git", fake_git)
    store = VaultGitStore(vault)
    item_id = store.publish("demand", _signal(1))
    rel = Path("exchange") / "demand" / f"{item_id}.json"
    assert (vault / rel).is_file()
    assert recorded[0] == ("add", "--", rel.as_posix())
    assert recorded[1] == ("commit", "-m", f"exchange demand {item_id}", "--", rel.as_posix())
    assert recorded[2][0] == "push"

    cursor = Cursor(vault / "state" / "exchange-cursor-demand")
    cursor.set(item_id)
    assert store.read("demand", since=cursor.get()) == []
