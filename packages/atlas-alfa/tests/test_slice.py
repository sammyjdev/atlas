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
    track.add(
        db_path, "e.md", title="Aceite", company="Epsilon", status="accepted", dossier_root=root
    )
    track.add(
        db_path, "f.md", title="Arquivo", company="Zeta", status="archived", dossier_root=root
    )
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert "Backend" in text
    assert "Oferta" in text
    assert "Recusa" not in text
    assert "Saida" not in text
    assert "Aceite" not in text
    assert "Arquivo" not in text
    assert "nova candidatura" not in text.lower()
    assert list(tmp_path.glob("*.db")) == [tmp_path / "merit.db"]


def test_status_moves_accepted_off_the_list(tmp_path, monkeypatch):
    db_path = _db(tmp_path, monkeypatch)
    root = tmp_path / "applications"
    app_id = track.add(
        db_path, "a.md", title="Backend", company="Acme", status="applied", dossier_root=root
    )
    client = TestClient(create_app())

    missing = client.post("/processos/99/status", data={"status": "accepted"})
    assert missing.status_code == 404

    invalid = client.post(f"/processos/{app_id}/status", data={"status": "ghosting"})
    assert invalid.status_code == 422
    assert "Backend" in client.get("/").text

    accepted = client.post(f"/processos/{app_id}/status", data={"status": "accepted"})
    assert accepted.status_code == 200
    assert "Backend" not in client.get("/").text


def _seed(tmp_path, monkeypatch):
    db_path = _db(tmp_path, monkeypatch)
    root = tmp_path / "applications"
    app_id = track.add(
        db_path, "a.md", title="Backend", company="Acme", status="applied", dossier_root=root
    )
    return root / f"{app_id}-backend", app_id


def test_recruiters_append_lines_and_need_https(tmp_path, monkeypatch):
    dossier, app_id = _seed(tmp_path, monkeypatch)
    client = TestClient(create_app())

    assert client.post("/processos/99/recrutador", data={"nome": "Ana"}).status_code == 404

    bad = client.post(
        f"/processos/{app_id}/recrutador", data={"nome": "Ana", "url": "http://x.example/ana"}
    )
    assert bad.status_code == 422
    assert not (dossier / "recrutador.md").exists()

    client.post(
        f"/processos/{app_id}/recrutador",
        data={"nome": "Ana", "url": "https://www.linkedin.com/in/ana"},
    )
    client.post(
        f"/processos/{app_id}/recrutador",
        data={"nome": "Bruno", "url": "https://www.linkedin.com/in/bruno"},
    )

    page = client.get(f"/processos/{app_id}").text
    assert "Ana" in page
    assert "https://www.linkedin.com/in/ana" in page
    assert "Bruno" in page


def test_reminder_keeps_datetime_and_data(tmp_path, monkeypatch):
    dossier, app_id = _seed(tmp_path, monkeypatch)
    client = TestClient(create_app())

    assert client.post("/processos/99/lembrete", data={"kind": "teste"}).status_code == 404

    no_date = client.post(f"/processos/{app_id}/lembrete", data={"kind": "teste", "dados": "x"})
    assert "Data obrigatoria." in no_date.text
    assert not (dossier / "lembrete.md").exists()

    ghost = client.post(
        f"/processos/{app_id}/lembrete",
        data={"kind": "ghosting", "quando": "2026-10-03T15:00:00Z", "dados": "x"},
    )
    assert ghost.status_code == 422
    assert not (dossier / "lembrete.md").exists()

    client.post(
        f"/processos/{app_id}/lembrete",
        data={"kind": "teste", "quando": "2026-10-03T15:00:00Z", "dados": "sala 2"},
    )

    page = client.get(f"/processos/{app_id}").text
    assert "2026-10-03T15:00:00Z" in page
    assert "sala 2" in page


def test_research_needs_a_pasted_url(tmp_path, monkeypatch):
    dossier, app_id = _seed(tmp_path, monkeypatch)
    from atlas_merit import fetch

    seen: list[str] = []

    def fake_fetch(url: str, timeout: int = 20) -> str:
        seen.append(url)
        return "Acme builds payment rails for clinics."

    monkeypatch.setattr(fetch, "fetch_posting", fake_fetch)
    client = TestClient(create_app())

    empty = client.get(f"/processos/{app_id}").text
    assert "Quer que eu pesquise" not in empty
    assert seen == []

    assert client.post("/processos/99/pesquisa", data={"url": "https://x"}).status_code == 404

    plain = client.post(
        f"/processos/{app_id}/pesquisa", data={"url": "http://example.com", "rotulo": "cliente"}
    )
    assert plain.status_code == 422
    assert seen == []

    found = client.post(
        f"/processos/{app_id}/pesquisa",
        data={"url": "https://example.com/about", "rotulo": "cliente"},
    )
    assert found.status_code == 200
    assert "cliente" in found.text
    assert "Acme builds payment rails" in found.text
    assert "Acme builds payment rails" in client.get(f"/processos/{app_id}").text
    assert (dossier / "pesquisa.md").is_file()


def test_research_fetch_failure_invents_nothing(tmp_path, monkeypatch):
    dossier, app_id = _seed(tmp_path, monkeypatch)
    from atlas_merit import fetch

    def broken(url: str, timeout: int = 20) -> str:
        raise OSError("connection refused")

    monkeypatch.setattr(fetch, "fetch_posting", broken)
    client = TestClient(create_app())

    response = client.post(
        f"/processos/{app_id}/pesquisa",
        data={"url": "https://example.com/about", "rotulo": "cliente"},
    )

    assert "Pesquisa indisponivel." in response.text
    assert not (dossier / "pesquisa.md").exists()


_PROFILE = """skills:
  - id: fastapi
    name: FastAPI
    status: strong
  - id: pytorch
    name: PyTorch
    status: gap
  - id: kafka
    name: Kafka
    status: gap
aliases: {}
"""


def _fit_section(html: str) -> str:
    import re

    match = re.search(r'<section id="fit">(.*?)</section>', html, re.S)
    assert match, "fit section missing"
    return re.sub(r"<[^>]+>", " ", match.group(1))


def test_fit_shows_stored_gap_verdict(tmp_path, monkeypatch):
    db_path = _db(tmp_path, monkeypatch)
    from atlas_merit.state import MeritState
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, START, StateGraph

    verdicts = [
        {"demand": "FastAPI", "verdict": "strong"},
        {"demand": "Rust async runtimes", "verdict": "gap"},
    ]
    graph = StateGraph(MeritState)
    graph.add_node("match", lambda _state: {"verdicts": verdicts})
    graph.add_edge(START, "match")
    graph.add_edge("match", END)
    with SqliteSaver.from_conn_string(db_path) as saver:
        graph.compile(checkpointer=saver).invoke({}, {"configurable": {"thread_id": "s-1"}})
    app_id = track.add(
        db_path, "a.md", title="Backend", company="Acme", status="applied",
        session_id="s-1", dossier_root=tmp_path / "applications",
    )

    page = TestClient(create_app()).get(f"/processos/{app_id}").text

    assert "Rust async runtimes" in _fit_section(page)


def test_fit_falls_back_to_rank_gap_names_without_number(tmp_path, monkeypatch):
    dossier, app_id = _seed(tmp_path, monkeypatch)
    profile = tmp_path / "profile.yaml"
    profile.write_text(_PROFILE, encoding="utf-8")
    monkeypatch.setenv("MERIT_PROFILE", str(profile))
    (dossier / "jd.md").write_text(
        "# Backend\n\nSeen on Indeed. FastAPI, PyTorch and Kafka required.\n", encoding="utf-8"
    )

    page = TestClient(create_app()).get(f"/processos/{app_id}").text
    fit = _fit_section(page)

    assert "PyTorch" in fit
    assert "Kafka" in fit
    assert not any(ch.isdigit() for ch in fit)
    assert "Indeed" not in page


def test_fit_survives_a_broken_profile(tmp_path, monkeypatch):
    _dossier, app_id = _seed(tmp_path, monkeypatch)
    profile = tmp_path / "profile.yaml"
    profile.write_text("skills: [unclosed\n", encoding="utf-8")
    monkeypatch.setenv("MERIT_PROFILE", str(profile))

    response = TestClient(create_app()).get(f"/processos/{app_id}")

    assert response.status_code == 200
    assert "Backend" in response.text


def test_gmail_confirm_appends_typed_note_only(tmp_path, monkeypatch):
    dossier, app_id = _seed(tmp_path, monkeypatch)
    db_path = str(tmp_path / "merit.db")
    client = TestClient(create_app())
    before = _count(db_path)

    assert client.post("/processos/99/gmail", data={"tipo": "proposta"}).status_code == 404

    no_type = client.post(f"/processos/{app_id}/gmail", data={"assunto": "Oferta"})
    assert no_type.status_code == 422
    assert "Oferta" not in (dossier / "notes.md").read_text(encoding="utf-8")

    ok = client.post(f"/processos/{app_id}/gmail", data={"tipo": "proposta", "assunto": "Oferta"})
    assert ok.status_code == 200
    notes = (dossier / "notes.md").read_text(encoding="utf-8")
    assert "tipo: proposta" in notes
    assert "Oferta" in notes
    assert _count(db_path) == before
    assert not (dossier / "lembrete.md").exists()


def _mail(sender: str, subject: str) -> bytes:
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = sender
    msg["Subject"] = subject
    msg.set_content("body")
    return msg.as_bytes()


def test_gmail_candidates_keep_only_actionable_mail():
    from atlas_alfa import gmail

    raws = [
        _mail("jobalerts-noreply@linkedin.com", "job alert: 30 new jobs"),
        _mail("Ana <ana@acme.example>", "interview Thursday 15:00"),
        _mail("news@acme.example", "Our latest newsletter"),
        _mail("rh@acme.example", "Proposta de trabalho"),
    ]

    found = gmail.candidates(raws)

    subjects = [c["assunto"] for c in found]
    assert "interview Thursday 15:00" in subjects
    assert not any("job alert" in s for s in subjects)
    assert "Our latest newsletter" not in subjects
    assert {"tipo": "proposta", "assunto": "Proposta de trabalho"} in found


_INTERVIEW = """---
title: Acme AI Engineer
nicho: interview
slug: acme-ai-engineer
cards:
- q: How would you evaluate a RAG pipeline in production?
  a: Names retrieval and answer metrics separately.
---

## Summary

Hard questions for Acme.

## Interview Q&A

How would you evaluate a RAG pipeline in production?
"""


def _vault(tmp_path, monkeypatch):
    root = tmp_path / "sage"
    (root / "vault" / "interview").mkdir(parents=True)
    (root / "vault" / "interview" / "acme-ai-engineer.md").write_text(_INTERVIEW, encoding="utf-8")
    monkeypatch.setenv("ATLAS_VAULT", str(root))
    return root


def test_prep_shows_a_picked_interview(tmp_path, monkeypatch):
    _dossier, app_id = _seed(tmp_path, monkeypatch)
    _vault(tmp_path, monkeypatch)
    client = TestClient(create_app())

    assert client.post("/processos/99/prep", data={"entrevista": "x"}).status_code == 404
    assert "Acme AI Engineer" in client.get(f"/processos/{app_id}").text

    shown = client.post(
        f"/processos/{app_id}/prep", data={"entrevista": "interview/acme-ai-engineer"}
    )
    assert shown.status_code == 200
    assert "How would you evaluate a RAG pipeline in production?" in shown.text
    assert "Front:" not in shown.text

    for bad in ("interview/nope", "../../merit"):
        missing = client.post(f"/processos/{app_id}/prep", data={"entrevista": bad})
        assert missing.status_code == 422
        assert "Hard questions for Acme" not in missing.text


def test_prep_anki_is_text_and_writes_no_deck(tmp_path, monkeypatch):
    _dossier, app_id = _seed(tmp_path, monkeypatch)
    _vault(tmp_path, monkeypatch)
    client = TestClient(create_app())

    anki = client.post(
        f"/processos/{app_id}/prep",
        data={"entrevista": "interview/acme-ai-engineer", "anki": "1"},
    )

    assert anki.status_code == 200
    assert "Front: How would you evaluate a RAG pipeline in production?" in anki.text
    assert "Back: Names retrieval and answer metrics separately." in anki.text
    assert list(tmp_path.rglob("*.apkg")) == []


def test_prep_without_vault_claims_nothing(tmp_path, monkeypatch):
    _dossier, app_id = _seed(tmp_path, monkeypatch)
    monkeypatch.delenv("ATLAS_VAULT", raising=False)
    client = TestClient(create_app())

    response = client.post(
        f"/processos/{app_id}/prep", data={"entrevista": "interview/acme-ai-engineer"}
    )

    assert "ATLAS_VAULT ausente." in response.text
    assert "How would you evaluate" not in response.text


def test_enviar_is_not_a_route(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    assert client.post("/enviar").status_code == 404


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
    from atlas_merit import fetch

    fetched: list[str] = []
    monkeypatch.setattr(fetch, "fetch_posting", lambda url, timeout=20: fetched.append(url) or "")
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
    assert "Quer que eu pesquise" not in pasted.text
    assert not (root / f"{app_id}-backend" / "pesquisa.md").exists()
    assert fetched == []
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
