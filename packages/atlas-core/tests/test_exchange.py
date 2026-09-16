from datetime import date

import pytest
from atlas_core import exchange
from atlas_core.contracts import DemandSignal, SkillDemand
from atlas_core.exchange import Cursor, LocalExchangeStore, new_id


def _signal(n: int) -> DemandSignal:
    return DemandSignal(
        id=f"sig-{n}",
        window_start=date(2026, 9, 1),
        window_end=date(2026, 9, 15),
        postings=n,
        skills=[SkillDemand(name="rag", count=n, share=1.0)],
    )


def test_ids_sort_in_publish_order():
    ids = [new_id() for _ in range(50)]
    assert ids == sorted(ids) and len(set(ids)) == 50


def test_publish_then_read_since_cursor(tmp_path):
    store = LocalExchangeStore(tmp_path)
    first = store.publish("demand", _signal(1))
    second = store.publish("demand", _signal(2))

    everything = store.read("demand")
    assert [i for i, _ in everything] == [first, second]
    assert everything[1][1]["id"] == "sig-2"

    assert [i for i, _ in store.read("demand", since=first)] == [second]
    assert store.read("demand", since=second) == []


def test_read_unknown_channel_is_empty(tmp_path):
    assert LocalExchangeStore(tmp_path).read("research") == []


def test_items_are_immutable_files(tmp_path):
    store = LocalExchangeStore(tmp_path)
    item_id = store.publish("demand", _signal(1))
    path = tmp_path / "demand" / f"{item_id}.json"
    with pytest.raises(FileExistsError):
        path.open("x")


def test_cursor_round_trip(tmp_path):
    cursor = Cursor(tmp_path / "cursors" / "sage.demand")
    assert cursor.get() is None
    cursor.set("abc")
    assert Cursor(tmp_path / "cursors" / "sage.demand").get() == "abc"


def test_ids_stay_ordered_within_one_clock_tick(monkeypatch):
    monkeypatch.setattr(exchange.time, "time_ns", lambda: 1_000)
    ids = [new_id() for _ in range(5)]
    assert ids == sorted(ids) and len(set(ids)) == 5
