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
        _msg("a3", "job alert: 30 new jobs", sender=mail.JOB_ALERT_SENDERS[0]),
        _msg("a4", "Our latest newsletter"),
        _msg("a5", "Re: Interview Thursday", labels=["SENT"]),
    ]

    found, skipped = gmail.from_mcp(items)

    assert found == []
    assert skipped == 0


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
