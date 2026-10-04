"""Actionable mail candidates. The user confirms each one; nothing here writes."""

import email
import email.policy
import email.utils
import re
from collections.abc import Iterable
from datetime import UTC, datetime

from atlas_merit import mail

# ponytail: keyword typing on the subject. First match wins, so order is policy.
TYPES = {
    "proposta": re.compile(r"\b(proposta|oferta|offer)\b", re.IGNORECASE),
    "horario": re.compile(r"\b(interview|entrevista|hor[aá]rio|schedule)\b", re.IGNORECASE),
    "teste": re.compile(r"\b(teste|test|assessment|desafio|challenge)\b", re.IGNORECASE),
    "feedback": re.compile(r"\b(feedback|retorno)\b", re.IGNORECASE),
}
SUBJECT_TERMS = (
    "proposta", "oferta", "offer", "entrevista", "interview", "horario", "schedule",
    "teste", "test", "assessment", "desafio", "challenge", "feedback", "retorno",
)
NOISE_SENDERS = (
    "notifications@github.com",
    "newsletters-noreply@linkedin.com",
    "team@mercor.com",
    "noreply+automations@airtableemail.com",
    *mail.JOB_ALERT_SENDERS,
)
NOISE_SUBJECT = re.compile(r"^canceled( event)?:|\blove your feedback\b", re.IGNORECASE)
QUERY = " ".join(
    [
        "newer_than:30d in:inbox -in:sent -category:promotions -category:social",
        *(f"-from:{sender}" for sender in NOISE_SENDERS),
        f"subject:({' OR '.join(SUBJECT_TERMS)})",
    ]
)
GMAIL_LINK = "https://mail.google.com/"
_ID = re.compile(r"[A-Za-z0-9]+")


def kind(subject: str) -> str | None:
    return next((name for name, pattern in TYPES.items() if pattern.search(subject)), None)


def key(item: dict) -> str:
    """Pending identity: one sender and one subject, whatever the Gmail id."""
    return f"{item['remetente'].lower()}|{item['assunto'].strip().lower()}"


def candidates(raws: Iterable[bytes]) -> list[dict[str, str]]:
    found = []
    for raw in raws:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        if mail.is_job_alert(msg):
            continue
        subject = str(msg["Subject"] or "").strip()
        tipo = kind(subject)
        if tipo:
            found.append({"tipo": tipo, "assunto": subject})
    return found


def _parse(item) -> dict | None:
    try:
        msg_id, sender, date = item["id"], item["sender"], item["date"]
        if not all(isinstance(v, str) for v in (msg_id, sender, date)):
            return None
        when = datetime.fromisoformat(date)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        when = when.astimezone(UTC)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    address = email.utils.parseaddr(sender)[1].lower()
    if not _ID.fullmatch(msg_id) or not address:
        return None
    labels = item.get("labelIds")
    labels = labels if isinstance(labels, list) else []
    link = item.get("viewUrl")
    subject = item.get("subject")
    return {
        "id": msg_id,
        "assunto": subject.strip() if isinstance(subject, str) else "",
        "remetente": address,
        "data": when.isoformat(),
        "importante": "IMPORTANT" in labels,
        "sent": "SENT" in labels,
        "link": link if isinstance(link, str) and link.startswith(GMAIL_LINK) else None,
    }


def from_mcp(items: Iterable) -> tuple[list[dict], int]:
    """search_threads messages -> (typed items, newest per sender+subject; skipped count)."""
    found: dict[str, dict] = {}
    skipped = 0
    for raw in items:
        item = _parse(raw)
        if item is None:
            skipped += 1
            continue
        tipo = kind(item["assunto"])
        noise = item["remetente"] in NOISE_SENDERS or NOISE_SUBJECT.search(item["assunto"])
        if item.pop("sent") or noise or tipo is None:
            continue
        item["tipo"] = tipo
        current = found.get(key(item))
        if current is None or item["data"] > current["data"]:
            found[key(item)] = item
    return list(found.values()), skipped
