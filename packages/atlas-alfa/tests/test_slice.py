import sys

import pytest
from atlas_alfa.app import create_app
from atlas_merit import track
from fastapi.testclient import TestClient


def _db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "merit.db")
    monkeypatch.setenv("MERIT_DB", db_path)
    monkeypatch.delenv("MERIT_API_KEY", raising=False)
    return db_path


def test_active_list_hides_terminal_and_keeps_offer(tmp_path, monkeypatch):
    db_path = _db(tmp_path, monkeypatch)
    root = tmp_path / "applications"
    track.add(db_path, "a.md", title="Backend", company="Acme", status="applied", dossier_root=root)
    track.add(db_path, "b.md", title="Oferta", company="Beta", status="offer", dossier_root=root)
    track.add(
        db_path, "c.md", title="Recusa", company="Gamma", status="rejected", dossier_root=root
    )
    track.add(
        db_path, "d.md", title="Saida", company="Delta", status="withdrawn", dossier_root=root
    )
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert "Backend" in text
    assert "Oferta" in text
    assert "Recusa" not in text
    assert "Saida" not in text
    assert "nova candidatura" not in text.lower()
    assert list(tmp_path.glob("*.db")) == [tmp_path / "merit.db"]


def _count(db_path: str) -> int:
    import contextlib

    with contextlib.closing(track._conn(db_path)) as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM applications").fetchone()["n"]


def test_paste_thread_updates_dossier_and_does_not_create(tmp_path, monkeypatch):
    db_path = _db(tmp_path, monkeypatch)
    root = tmp_path / "applications"
    app_id = track.add(
        db_path, "a.md", title="Backend", company="Acme", status="applied", dossier_root=root
    )
    client = TestClient(create_app())
    before = _count(db_path)

    missing = client.post("/processos/99/thread", data={"text": "oi"})
    assert missing.status_code == 404
    assert _count(db_path) == before

    empty = client.post(f"/processos/{app_id}/thread", data={"text": "   "})
    assert empty.status_code == 200
    assert "vazio" in empty.text.lower()

    pasted = client.post(
        f"/processos/{app_id}/thread",
        data={"text": "Oi, temos uma vaga https://example.com/about"},
    )
    assert pasted.status_code == 200
    assert "Oi, temos uma vaga" in pasted.text
    assert "pesquis" not in pasted.text.lower()
    assert _count(db_path) == before
    thread = (root / f"{app_id}-backend" / "thread.md").read_text(encoding="utf-8")
    assert "Oi, temos uma vaga https://example.com/about" in thread


def _seed_thread(tmp_path, monkeypatch, body: str = "Podemos conversar amanha?"):
    db_path = _db(tmp_path, monkeypatch)
    root = tmp_path / "applications"
    app_id = track.add(
        db_path, "a.md", title="Backend", company="Acme", status="applied", dossier_root=root
    )
    track.log(db_path, app_id, body, file="thread", dossier_root=root)
    return db_path, app_id


def test_draft_without_model_is_not_invented(tmp_path, monkeypatch):
    _db_path, app_id = _seed_thread(tmp_path, monkeypatch)
    client = TestClient(create_app())

    response = client.post(f"/processos/{app_id}/rascunho")

    assert response.status_code == 200
    assert "Sem modelo" in response.text
    assert "Você envia" in response.text
    assert "indeed" not in response.text.lower()


def test_draft_shows_model_text_and_canon_in_prompt(tmp_path, monkeypatch):
    _db_path, app_id = _seed_thread(tmp_path, monkeypatch)
    seen: list[str] = []

    def complete(prompt: str) -> str:
        seen.append(prompt)
        return (
            "Resumo: conversa inicial\n"
            "Prazos: nenhum\n"
            "Proximo passo: responder\n"
            "Rascunho: Posso falar na quinta."
        )

    client = TestClient(create_app(complete))
    response = client.post(f"/processos/{app_id}/rascunho")

    assert response.status_code == 200
    assert "Posso falar na quinta." in response.text
    assert "Você envia" in response.text
    prompt = seen[0]
    assert "7 anos" in prompt or "7 years" in prompt
    assert "TJPB" in prompt
    assert "2019" in prompt
    assert "2022" in prompt
    assert "2025" in prompt
    assert "Databricks" in prompt
    assert "Afya" in prompt
    assert "Podemos conversar amanha?" in prompt


def test_draft_blocks_canon_violation_without_echoing_it(tmp_path, monkeypatch):
    _db_path, app_id = _seed_thread(tmp_path, monkeypatch)

    def complete(_prompt: str) -> str:
        return "Rascunho: trabalhei na Afya por six years."

    client = TestClient(create_app(complete))
    response = client.post(f"/processos/{app_id}/rascunho")

    assert response.status_code == 200
    assert "bloqueado" in response.text.lower()
    assert "Afya" not in response.text
    assert "six years" not in response.text.lower()


def test_draft_without_thread_does_not_call_model(tmp_path, monkeypatch):
    db_path = _db(tmp_path, monkeypatch)
    root = tmp_path / "applications"
    app_id = track.add(
        db_path, "a.md", title="Backend", company="Acme", status="applied", dossier_root=root
    )
    called = False

    def complete(_prompt: str) -> str:
        nonlocal called
        called = True
        return "Rascunho: nao devia"

    client = TestClient(create_app(complete))
    response = client.post(f"/processos/{app_id}/rascunho")

    assert response.status_code == 200
    assert called is False
    assert "nao devia" not in response.text


def test_bad_port_exits_with_usage(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["alfa", "--port", "abc"])
    from atlas_alfa.cli import main

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert "uso:" in capsys.readouterr().err
