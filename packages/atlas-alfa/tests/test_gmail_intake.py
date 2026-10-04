import io
import json
import stat
import sys

from atlas_alfa import gmail
from atlas_merit import mail


def _msg(
    msg_id: str,
    subject: str,
    sender: str = "rh@acme.example",
    date: str = "2026-10-02T02:40:58Z",
    labels: list[str] | None = None,
    link: str | None = "https://mail.google.com/mail/#all/thread-f:1",
) -> dict:
    item = {"id": msg_id, "threadId": msg_id, "subject": subject, "sender": sender, "date": date}
    if labels is not None:
        item["labelIds"] = labels
    if link is not None:
        item["viewUrl"] = link
    return item


def test_from_mcp_drops_noise_senders_and_untyped_subjects():
    items = [
        _msg("a1", "Run failed: test - main", sender="notifications@github.com"),
        _msg("a2", "Coding Challenge #139", sender="newsletters-noreply@linkedin.com"),
        _msg("a3", "Your Video Interview Awaits", sender=mail.JOB_ALERT_SENDERS[0]),
        _msg("a4", "Our latest newsletter"),
        _msg("a5", "Re: Interview Thursday", labels=["SENT"]),
    ]

    found, skipped = gmail.from_mcp(items)

    assert found == []
    assert skipped == 0


def test_from_mcp_drops_owner_noise_from_the_first_real_pull():
    items = [
        _msg("b1", "Instant Work Offer: Paid Research", sender="team@mercor.com"),
        _msg("b2", "Ready to Shine? Your Video Interview Awaits!",
             sender="noreply+automations@airtableemail.com"),
        _msg("b3", "Canceled: Senior AI Engineer/Agentic Interview"),
        _msg("b4", "Canceled event: Interview with Acme @ Mon"),
        _msg("b5", "Acme - We\u2019d love your feedback"),
        _msg("b6", "Interview feedback for your application"),
        _msg("b7", "Interview feedback: we love your feedback round, next step"),
        _msg("b8", "Acme - We'd love your feedback"),
    ]

    found, _ = gmail.from_mcp(items)

    assert sorted(item["id"] for item in found) == ["b6", "b7"]
    assert all(f"-from:{s}" in gmail.QUERY for s in ("team@mercor.com",
                                                     "noreply+automations@airtableemail.com"))


def test_from_mcp_keeps_typed_mail_with_importance():
    found, _ = gmail.from_mcp(
        [
            _msg("b1", "Your Video Interview Awaits", labels=["INBOX", "IMPORTANT"]),
            _msg("b2", "Proposta de trabalho", sender="Ana <ana@beta.example>"),
        ]
    )

    by_id = {item["id"]: item for item in found}
    assert by_id["b1"]["tipo"] == "horario"
    assert by_id["b1"]["assunto"] == "Your Video Interview Awaits"
    assert by_id["b1"]["remetente"] == "rh@acme.example"
    assert by_id["b1"]["data"] == "2026-10-02T02:40:58+00:00"
    assert by_id["b1"]["importante"] is True
    assert by_id["b2"]["importante"] is False
    assert by_id["b2"]["remetente"] == "ana@beta.example"


def test_from_mcp_collapses_repeats_to_the_newest():
    found, _ = gmail.from_mcp(
        [
            _msg("c1", "Your Video Interview Awaits", date="2026-09-28T02:41:12Z"),
            _msg(
                "c2",
                "  your video interview awaits ",
                sender="RH@Acme.example",
                date="2026-10-02T02:40:58Z",
            ),
            _msg("c3", "Your Video Interview Awaits", date="2026-09-30T02:41:11Z"),
        ]
    )

    assert len(found) == 1
    assert found[0]["id"] == "c2"
    assert found[0]["data"] == "2026-10-02T02:40:58+00:00"


def test_from_mcp_keeps_only_gmail_links():
    found, _ = gmail.from_mcp(
        [
            _msg("d1", "Proposta", link="https://evil.example/phish"),
            _msg("d2", "Feedback do processo", sender="rh@beta.example"),
        ]
    )

    by_id = {item["id"]: item for item in found}
    assert by_id["d1"]["link"] is None
    assert by_id["d2"]["link"] == "https://mail.google.com/mail/#all/thread-f:1"


def test_from_mcp_skips_malformed_items_and_keeps_the_rest():
    items = [
        {"subject": "Proposta", "sender": "rh@acme.example", "date": "2026-10-02T02:40:58Z"},
        _msg("e2", "Proposta", date="ontem"),
        _msg("../e3", "Proposta"),
        {"id": "e4", "subject": "Proposta", "date": "2026-10-02T02:40:58Z"},
        "not a message",
        _msg("e6", "Teste tecnico"),
    ]

    found, skipped = gmail.from_mcp(items)

    assert [item["id"] for item in found] == ["e6"]
    assert skipped == 5


def test_query_is_built_from_the_noise_senders():
    assert "newer_than:30d" in gmail.QUERY
    assert "in:inbox" in gmail.QUERY
    for sender in gmail.NOISE_SENDERS:
        assert f"-from:{sender}" in gmail.QUERY


def _run(monkeypatch, capsys, args, stdin=""):
    monkeypatch.setattr(sys, "argv", ["alfa", *args])
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    from atlas_alfa.cli import main

    code = 0
    try:
        main()
    except SystemExit as exit_:
        code = exit_.code
    out = capsys.readouterr()
    return code, out.out, out.err


def _pending_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MERIT_DB", str(tmp_path / "merit.db"))
    return tmp_path / "gmail-pendentes.json"


def _batch():
    return [
        _msg("f1", "Your Video Interview Awaits", labels=["INBOX", "IMPORTANT"]),
        _msg("f2", "Proposta de trabalho", sender="ana@beta.example"),
        _msg("f3", "Run failed: test - main", sender="notifications@github.com"),
        "not a message",
    ]


def test_candidatos_lands_filtered_items_in_a_private_file(tmp_path, monkeypatch, capsys):
    path = _pending_file(tmp_path, monkeypatch)

    code, out, err = _run(monkeypatch, capsys, ["gmail-candidatos"], json.dumps(_batch()))

    assert code == 0
    assert out.strip() == "2"
    assert "1" in err
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    pending = json.loads(path.read_text())["pending"]
    assert sorted(item["id"] for item in pending) == ["f1", "f2"]


def test_candidatos_is_quiet_on_stderr_without_skips(tmp_path, monkeypatch, capsys):
    _pending_file(tmp_path, monkeypatch)

    code, out, err = _run(monkeypatch, capsys, ["gmail-candidatos"], json.dumps(_batch()[:2]))

    assert code == 0 and out.strip() == "2" and err == ""


def test_candidatos_twice_adds_nothing(tmp_path, monkeypatch, capsys):
    _pending_file(tmp_path, monkeypatch)
    _run(monkeypatch, capsys, ["gmail-candidatos"], json.dumps(_batch()))

    code, out, _ = _run(monkeypatch, capsys, ["gmail-candidatos"], json.dumps(_batch()))

    assert code == 0 and out.strip() == "0"


def test_candidatos_keeps_one_item_per_key_with_the_newest_date(tmp_path, monkeypatch, capsys):
    path = _pending_file(tmp_path, monkeypatch)
    _run(monkeypatch, capsys, ["gmail-candidatos"], json.dumps(_batch()))
    later = [_msg("g1", "your video interview awaits", date="2026-10-03T08:00:00Z")]

    code, out, _ = _run(monkeypatch, capsys, ["gmail-candidatos"], json.dumps(later))

    pending = json.loads(path.read_text())["pending"]
    assert code == 0 and out.strip() == "0"
    assert len(pending) == 2
    interview = next(item for item in pending if item["tipo"] == "horario")
    assert interview["data"] == "2026-10-03T08:00:00+00:00"


def test_candidatos_rejects_non_list_input_without_touching_the_file(
    tmp_path, monkeypatch, capsys
):
    path = _pending_file(tmp_path, monkeypatch)
    _run(monkeypatch, capsys, ["gmail-candidatos"], json.dumps(_batch()))
    before = path.read_bytes()

    for bad in ['{"id": "x"}', "not json"]:
        code, _, err = _run(monkeypatch, capsys, ["gmail-candidatos"], bad)
        assert code == 2 and "uso:" in err
    assert path.read_bytes() == before


def test_candidatos_refuses_an_unreadable_pending_file(tmp_path, monkeypatch, capsys):
    path = _pending_file(tmp_path, monkeypatch)

    for broken in [b"{broken", b"[]"]:
        path.write_bytes(broken)
        code, _, err = _run(monkeypatch, capsys, ["gmail-candidatos"], json.dumps(_batch()))
        assert code == 2 and "pendentes ilegivel" in err
        assert path.read_bytes() == broken


def test_gmail_query_prints_the_query(monkeypatch, capsys):
    code, out, _ = _run(monkeypatch, capsys, ["gmail-query"])

    assert code == 0 and out.strip() == gmail.QUERY


def _item(msg_id, assunto, tipo, data="2026-10-02T02:40:58+00:00", importante=False):
    return {
        "id": msg_id,
        "tipo": tipo,
        "assunto": assunto,
        "remetente": f"rh-{msg_id}@acme.example",
        "data": data,
        "importante": importante,
        "link": "https://mail.google.com/mail/#all/thread-f:1",
    }


def _seed_pending(tmp_path, monkeypatch, items, seen=()):
    path = _pending_file(tmp_path, monkeypatch)
    path.write_text(json.dumps({"pending": items, "seen": list(seen)}), encoding="utf-8")
    return path


def _client():
    from atlas_alfa.app import create_app
    from fastapi.testclient import TestClient

    return TestClient(create_app())


def test_gmail_page_lists_items_and_only_active_processes(tmp_path, monkeypatch):
    from atlas_merit import track

    _seed_pending(
        tmp_path,
        monkeypatch,
        [_item("h1", "Proposta Acme", "proposta"), _item("h2", "Feedback Beta", "feedback")],
    )
    db_path = str(tmp_path / "merit.db")
    root = tmp_path / "applications"
    track.add(db_path, "a.md", title="Backend", company="Acme", status="applied", dossier_root=root)
    track.add(
        db_path, "b.md", title="Recusa", company="Gamma", status="rejected", dossier_root=root
    )

    page = _client().get("/gmail")

    assert page.status_code == 200
    for text in ("Proposta Acme", "Feedback Beta", "proposta", "feedback", "Backend"):
        assert text in page.text
    assert "Recusa" not in page.text


def test_gmail_page_empty_state(tmp_path, monkeypatch):
    _pending_file(tmp_path, monkeypatch)
    assert "Nenhum e-mail pendente." in _client().get("/gmail").text

    _seed_pending(tmp_path, monkeypatch, [])
    assert "Nenhum e-mail pendente." in _client().get("/gmail").text


def test_index_shows_the_pending_count(tmp_path, monkeypatch):
    _seed_pending(
        tmp_path,
        monkeypatch,
        [_item("i1", "Proposta Acme", "proposta"), _item("i2", "Feedback Beta", "feedback")],
    )

    page = _client().get("/").text

    assert "E-mails pendentes: 2" in page
    assert 'href="/gmail"' in page


def test_gmail_page_orders_important_then_type_then_newest(tmp_path, monkeypatch):
    _seed_pending(
        tmp_path,
        monkeypatch,
        [
            _item("j1", "Assunto A", "feedback", "2026-09-20T10:00:00+00:00", importante=True),
            _item("j2", "Assunto B", "proposta", "2026-10-02T10:00:00+00:00"),
            _item("j3", "Assunto C", "horario", "2026-09-25T10:00:00+00:00", importante=True),
            _item("j4", "Assunto D", "horario", "2026-09-30T10:00:00+00:00", importante=True),
        ],
    )

    text = _client().get("/gmail").text

    order = [text.index(f"Assunto {letter}") for letter in "DCAB"]
    assert order == sorted(order)


def test_gmail_page_reports_an_unreadable_file_without_rewriting(tmp_path, monkeypatch):
    path = _pending_file(tmp_path, monkeypatch)
    path.write_bytes(b"{broken")
    client = _client()

    page = client.get("/gmail")

    assert "Arquivo de pendentes ilegivel." in page.text
    assert client.get("/").status_code == 200
    assert path.read_bytes() == b"{broken"


def test_from_mcp_skips_a_date_that_overflows_utc():
    items = [_msg("k1", "Teste tecnico", date="0001-01-01T00:00:00+01:00"), _msg("k2", "Teste")]

    found, skipped = gmail.from_mcp(items)

    assert [item["id"] for item in found] == ["k2"] and skipped == 1


def test_candidatos_keeps_0600_over_leftover_open_files(tmp_path, monkeypatch, capsys):
    path = _pending_file(tmp_path, monkeypatch)
    for leftover in (f"{path.name}.tmp", f"{path.name}.lock"):
        (tmp_path / leftover).write_text("")
        (tmp_path / leftover).chmod(0o644)

    code, _, _ = _run(monkeypatch, capsys, ["gmail-candidatos"], json.dumps(_batch()))

    assert code == 0
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / f"{path.name}.lock").stat().st_mode) == 0o600


def _app_with_pending(tmp_path, monkeypatch, status="applied"):
    from atlas_merit import track

    _seed_pending(tmp_path, monkeypatch, [_item("m1", "Proposta Acme", "proposta")])
    db_path = str(tmp_path / "merit.db")
    app_id = track.add(
        db_path, "a.md", title="Backend", company="Acme", status=status,
        dossier_root=tmp_path / "applications",
    )
    return db_path, app_id


def _notes(db_path, app_id, file="notes"):
    from atlas_merit import track

    return [body for _, source, body in track.entries(db_path, app_id) if source == file]


def _apps(db_path):
    import contextlib

    from atlas_merit import track

    with contextlib.closing(track._conn(db_path)) as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM applications").fetchone()["n"]


def test_confirm_writes_one_tagged_note_and_clears_the_item(tmp_path, monkeypatch):
    db_path, app_id = _app_with_pending(tmp_path, monkeypatch)
    client = _client()
    before = _apps(db_path)

    response = client.post("/gmail/m1/confirmar", data={"processo": str(app_id)})

    assert response.status_code == 200
    notes = _notes(db_path, app_id)
    assert len(notes) == 1
    for text in ("proposta", "Proposta Acme", "rh-m1@acme.example", "gmail: m1"):
        assert text in notes[0]
    assert _notes(db_path, app_id, "lembrete") == []
    assert "Proposta Acme" not in client.get("/gmail").text
    assert _apps(db_path) == before


def test_confirm_needs_an_active_process(tmp_path, monkeypatch):
    from atlas_merit import track

    db_path, app_id = _app_with_pending(tmp_path, monkeypatch)
    closed = track.add(
        db_path, "b.md", title="Recusa", company="Gamma", status="rejected",
        dossier_root=tmp_path / "applications",
    )
    client = _client()

    for data in ({}, {"processo": "999"}, {"processo": "abc"}, {"processo": str(closed)}):
        response = client.post("/gmail/m1/confirmar", data=data)
        assert response.status_code == 422
    assert "Proposta Acme" in client.get("/gmail").text
    assert _notes(db_path, app_id) == [] and _notes(db_path, closed) == []


def test_confirm_unknown_item_is_404(tmp_path, monkeypatch):
    _db_path, app_id = _app_with_pending(tmp_path, monkeypatch)

    response = _client().post("/gmail/nope/confirmar", data={"processo": str(app_id)})

    assert response.status_code == 404


def test_confirm_twice_writes_one_note(tmp_path, monkeypatch):
    from atlas_merit import track

    db_path, app_id = _app_with_pending(tmp_path, monkeypatch)
    track.log(
        db_path, app_id, "tipo: proposta\ngmail: m1", file="notes",
        dossier_root=tmp_path / "applications",
    )
    client = _client()

    response = client.post("/gmail/m1/confirmar", data={"processo": str(app_id)})

    assert response.status_code == 200
    assert len(_notes(db_path, app_id)) == 1
    assert "Proposta Acme" not in client.get("/gmail").text


def test_discard_drops_the_item_without_a_note(tmp_path, monkeypatch):
    db_path, app_id = _app_with_pending(tmp_path, monkeypatch)
    client = _client()

    assert client.post("/gmail/nope/descartar").status_code == 404
    response = client.post("/gmail/m1/descartar")

    assert response.status_code == 200
    assert "Proposta Acme" not in client.get("/gmail").text
    assert _notes(db_path, app_id) == []


def test_confirmed_or_discarded_keys_do_not_come_back(tmp_path, monkeypatch, capsys):
    from atlas_merit import track

    _pending_file(tmp_path, monkeypatch)
    app_id = track.add(
        str(tmp_path / "merit.db"), "a.md", title="Backend", company="Acme", status="applied",
        dossier_root=tmp_path / "applications",
    )
    _run(monkeypatch, capsys, ["gmail-candidatos"], json.dumps(_batch()))
    client = _client()
    client.post("/gmail/f1/confirmar", data={"processo": str(app_id)})
    client.post("/gmail/f2/descartar")
    again = [
        _msg("f1", "Your Video Interview Awaits"),
        _msg("n1", "your video interview awaits", date="2026-10-04T08:00:00Z"),
        _msg("f2", "Proposta de trabalho", sender="ana@beta.example"),
        _msg("n2", "Proposta de trabalho", sender="Ana <ANA@beta.example>"),
    ]

    code, out, _ = _run(monkeypatch, capsys, ["gmail-candidatos"], json.dumps(again))

    assert code == 0 and out.strip() == "0"
    assert "Nenhum e-mail pendente." in client.get("/gmail").text


def test_intake_doc_names_the_steps_and_the_limits():
    import re
    from pathlib import Path

    doc = Path(__file__).resolve().parents[3] / "docs" / "gmail-intake.md"
    text = doc.read_text(encoding="utf-8")

    names = ("alfa gmail-query", "search_threads", "alfa gmail-candidatos")
    steps = [text.index(name) for name in names]
    assert steps == sorted(steps)
    assert "Only `search_threads`" in text
    assert "never sends" in text
    assert re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", text) == []
    assert "/Users/" not in text and "/home/" not in text
    assert not re.search(r"\.local\b|\.ts\.net|\.lan\b|192\.168\.|\b10\.\d+\.", text)


def test_confirm_tag_cannot_be_forged_by_the_subject(tmp_path, monkeypatch):
    from atlas_merit import track

    _seed_pending(
        tmp_path,
        monkeypatch,
        [_item("p1", "Proposta\ngmail: p2", "proposta"), _item("p2", "Feedback Beta", "feedback")],
    )
    db_path = str(tmp_path / "merit.db")
    app_id = track.add(
        db_path, "a.md", title="Backend", company="Acme", status="applied",
        dossier_root=tmp_path / "applications",
    )
    client = _client()

    client.post("/gmail/p1/confirmar", data={"processo": str(app_id)})
    client.post("/gmail/p2/confirmar", data={"processo": str(app_id)})

    notes = _notes(db_path, app_id)
    assert len(notes) == 2
    assert "Feedback Beta" in notes[1]


def test_confirm_rejects_odd_process_numbers(tmp_path, monkeypatch):
    db_path, app_id = _app_with_pending(tmp_path, monkeypatch)
    client = _client()

    for raw in ("²", "9" * 30, "-1", "0"):
        assert client.post("/gmail/m1/confirmar", data={"processo": raw}).status_code == 422
    assert "Proposta Acme" in client.get("/gmail").text
    assert _notes(db_path, app_id) == []


def test_manual_form_cannot_plant_a_gmail_tag(tmp_path, monkeypatch):
    db_path, app_id = _app_with_pending(tmp_path, monkeypatch)
    client = _client()

    client.post(
        f"/processos/{app_id}/gmail", data={"tipo": "proposta", "assunto": "x\ngmail: m1"}
    )
    client.post("/gmail/m1/confirmar", data={"processo": str(app_id)})

    notes = _notes(db_path, app_id)
    assert len(notes) == 2
    assert "Proposta Acme" in notes[1]
