from datetime import date
from pathlib import Path

from atlas_core.contracts import DemandSignal, SkillDemand
from atlas_core.exchange import Cursor, LocalExchangeStore

from atlas_sage import main
from atlas_sage.jds import newest_demand_signal, topic_source_texts
from atlas_sage.state import State


def _signal(name: str) -> DemandSignal:
    return DemandSignal(
        id="sig",
        window_start=date(2026, 9, 1),
        window_end=date(2026, 9, 15),
        postings=1,
        skills=[SkillDemand(name=name, count=1, share=1.0)],
    )


def test_topic_source_lowercases_skill_names(tmp_path: Path) -> None:
    LocalExchangeStore(tmp_path / "exchange").publish("demand", _signal("FastAPI"))
    jds = tmp_path / "jds"
    jds.mkdir()
    assert topic_source_texts(tmp_path, jds) == ["fastapi"]


def test_topic_source_prefers_newest_valid_signal_over_jds(tmp_path: Path) -> None:
    store = LocalExchangeStore(tmp_path / "exchange")
    store.publish("demand", _signal("virtual threads"))
    jds = tmp_path / "inputs" / "jds"
    jds.mkdir(parents=True)
    (jds / "role.md").write_text("attention mechanism only")
    texts = topic_source_texts(tmp_path, jds)
    assert "virtual threads" in texts[0]
    assert "attention" not in texts[0]


def test_topic_source_falls_back_when_dir_missing_empty_or_invalid(tmp_path: Path) -> None:
    jds = tmp_path / "jds"
    jds.mkdir()
    (jds / "role.md").write_text("Java engineer")
    assert topic_source_texts(tmp_path, jds) == ["java engineer"]
    demand = tmp_path / "exchange" / "demand"
    demand.mkdir(parents=True)
    assert topic_source_texts(tmp_path, jds) == ["java engineer"]
    (demand / "0001-bad.json").write_text("{not json")
    assert topic_source_texts(tmp_path, jds) == ["java engineer"]
    assert newest_demand_signal(tmp_path) is None


def test_topic_source_takes_newest_of_several_signals(tmp_path: Path) -> None:
    store = LocalExchangeStore(tmp_path / "exchange")
    store.publish("demand", _signal("rag"))
    store.publish("demand", _signal("virtual threads"))
    assert topic_source_texts(tmp_path, tmp_path / "jds") == ["virtual threads"]


def test_valid_signal_without_skills_still_beats_jds(tmp_path: Path) -> None:
    empty = _signal("x").model_copy(update={"skills": []})
    LocalExchangeStore(tmp_path / "exchange").publish("demand", empty)
    jds = tmp_path / "jds"
    jds.mkdir()
    (jds / "role.md").write_text("Java engineer")
    assert topic_source_texts(tmp_path, jds) == [""]


def test_invalid_file_after_valid_does_not_move_cursor(tmp_path: Path) -> None:
    good = LocalExchangeStore(tmp_path / "exchange").publish("demand", _signal("rag"))
    (tmp_path / "exchange" / "demand" / "99999999999999999999-bad.json").write_text("{")
    assert topic_source_texts(tmp_path, tmp_path / "jds") == ["rag"]
    assert Cursor(tmp_path / "state" / "exchange-cursor-demand").get() == good


def test_consumed_signals_are_not_reread_and_stale_still_wins(
    tmp_path: Path, monkeypatch
) -> None:
    store = LocalExchangeStore(tmp_path / "exchange")
    store.publish("demand", _signal("rag"))
    last = store.publish("demand", _signal("virtual threads"))
    assert topic_source_texts(tmp_path, tmp_path / "jds") == ["virtual threads"]
    read: list[str] = []
    original = Path.read_text

    def spy(self: Path, *args, **kwargs) -> str:
        if self.suffix == ".json":
            read.append(self.stem)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    assert topic_source_texts(tmp_path, tmp_path / "jds") == ["virtual threads"]
    assert read == [last]


def test_exchange_cursor_no_reread(tmp_path: Path) -> None:
    store = LocalExchangeStore(tmp_path / "exchange")
    first = store.publish("demand", _signal("rag"))
    cursor = Cursor(tmp_path / "state" / "exchange-cursor-demand")
    cursor.set(first)
    assert store.read("demand", since=cursor.get()) == []


def test_refill_queue_prefers_demand_signal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_VAULT", str(tmp_path))
    syllabus = tmp_path / "inputs" / "syllabus.yaml"
    syllabus.parent.mkdir()
    syllabus.write_text(
        "java:\n  - records and sealed classes\n  - virtual threads (JEP 444)\n"
    )
    jds = tmp_path / "inputs" / "jds"
    jds.mkdir()
    (jds / "role.md").write_text("Looking for records and sealed classes")
    sig = LocalExchangeStore(tmp_path / "exchange").publish("demand", _signal("virtual threads"))
    state = State()
    main.refill_queue(state)
    assert state.queue[0]["topic"] == "virtual threads (JEP 444)"
    assert Cursor(tmp_path / "state" / "exchange-cursor-demand").get() == sig
