"""Actionable mail candidates. The user confirms each one; nothing here writes."""

import email
import email.policy
import re
from collections.abc import Iterable

from atlas_merit import mail

# ponytail: keyword typing on the subject. First match wins, so order is policy.
TYPES = {
    "proposta": re.compile(r"\b(proposta|oferta|offer)\b", re.IGNORECASE),
    "horario": re.compile(r"\b(interview|entrevista|hor[aá]rio|schedule)\b", re.IGNORECASE),
    "teste": re.compile(r"\b(teste|test|assessment|desafio|challenge)\b", re.IGNORECASE),
    "feedback": re.compile(r"\b(feedback|retorno)\b", re.IGNORECASE),
}


def kind(subject: str) -> str | None:
    return next((name for name, pattern in TYPES.items() if pattern.search(subject)), None)


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
