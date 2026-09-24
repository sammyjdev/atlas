"""The live interview loop: what happens after the candidate answers.

The static pipeline is not replaced by this, it becomes the planning step. The
plan document already holds 8-12 questions each with a
3-5 point rubric, written by the writer and hardened by the adversarial critic.
That is exactly what an interviewer needs before walking into a room: an agenda
and a grading key, produced offline for $0.002. So the cron plans and the
terminal conducts, and a session opens with no model call and no silence.

One model call per turn returns the judgment and the next utterance together.
That is not the writer approving its own work - the thing being judged is a
HUMAN's answer, against a rubric written offline by a writer/critic pair that
already survived an adversarial pass. The rubric is the external anchor.

What a mock cannot check is whether the follow-up actually reacts to what was
said: a generic "interesting, and how would you measure that?" fits after any
answer and reads as adaptive. scripts/probe_followup_sensitivity.py measures
that against the real models by answering the same question two opposite ways.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .parser import ParseError, _evidence

# How many times the interviewer may press the same question before moving on.
#
# Twenty minutes is the entire budget and a model that keeps finding one more
# thing to probe will spend all of it on question one. Two presses is enough to
# separate "did not explain it well" from "does not know it".
MAX_PRESSES = 2

# Hard stop on the session. Twenty minutes is roughly 13 turns clean and 25 with
# presses, against plans that hold 8-12 questions.
DEFAULT_MAX_TURNS = 20


@dataclass(frozen=True)
class TurnDecision:
    """What the interviewer decided after one answer."""

    covered: list[str]
    missing: list[str]
    verdict: str
    say: str


def parse_turn(text: str) -> TurnDecision:
    """Read the model's turn, refusing the shapes that make a bad interviewer.

    An `accept` with nothing in `covered` is coerced to `press`. Letting the
    candidate off the hook has to cost the interviewer something - it must name
    which rubric bullet the answer satisfied - and a model will otherwise accept
    a non-answer politely all day. Enforced here rather than asked for in the
    prompt, because prompts do not hold under a pleasant non-answer.
    """
    start = text.find("{")
    if start == -1:
        raise ParseError("no JSON object in interviewer turn" + _evidence(text))
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as e:
        raise ParseError(f"invalid interviewer JSON: {e}" + _evidence(text))

    say = str(data.get("say") or "").strip()
    if not say:
        raise ParseError("interviewer produced no utterance" + _evidence(text))

    covered = [str(c) for c in (data.get("covered") or [])]
    verdict = str(data.get("verdict") or "press").strip().lower()
    if verdict == "accept" and not covered:
        verdict = "press"
    if verdict not in ("accept", "press"):
        verdict = "press"

    return TurnDecision(
        covered=covered,
        missing=[str(m) for m in (data.get("missing") or [])],
        verdict=verdict,
        say=say,
    )


@dataclass
class LiveSession:
    """Position in the plan, and the transcript so far."""

    plan: dict
    max_turns: int = DEFAULT_MAX_TURNS
    question_index: int = 0
    presses: int = 0
    turns: list[tuple[str, str]] = field(default_factory=list)

    @property
    def cards(self) -> list[dict]:
        return self.plan.get("cards") or []

    @property
    def finished(self) -> bool:
        return (
            self.question_index >= len(self.cards) or len(self.turns) >= self.max_turns
        )

    def current_card(self) -> dict | None:
        if self.question_index < len(self.cards):
            return self.cards[self.question_index]
        return None

    def asked(self) -> list[str]:
        """Questions the session actually reached.

        The closing verdict grades these and nothing else. Summarising a
        question that was never asked is the easiest way to produce a
        confident, wrong assessment.
        """
        return [str(c.get("q", "")) for c in self.cards[: self.question_index]]

    def record(self, speaker: str, text: str) -> None:
        self.turns.append((speaker, text))

    def apply(self, decision: TurnDecision) -> None:
        self.turns.append(("interviewer", decision.say))
        if decision.verdict == "accept":
            self.question_index += 1
            self.presses = 0
            return
        self.presses += 1
        if self.presses > MAX_PRESSES:
            self.question_index += 1
            self.presses = 0
