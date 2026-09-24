"""The live turn loop: the decision after each answer.

These test the machinery, not the model. Whether the follow-up actually reacts
to what the candidate said is a property of the model and cannot be asserted
with a mock - see scripts/probe_followup_sensitivity.py, which measures it
against the real ones.
"""

import json

import pytest

from atlas_sage.live import (
    MAX_PRESSES,
    LiveSession,
    TurnDecision,
    parse_turn,
)
from atlas_sage.parser import ParseError

PLAN = {
    "vaga": "Acme - Senior AI Engineer",
    "cards": [
        {
            "q": "Your RAG returns stale answers. Retrieval or prompt?",
            "a": "- Names retrieval first\n- Gives a separating check\n- States a number",
        },
        {
            "q": "You have no LoRA experience. The role requires it.",
            "a": "- Names adjacent work\n- Says what they would read first\n- No bluffing",
        },
    ],
}


def _decision(**kw) -> str:
    body = {"covered": [], "missing": ["x"], "verdict": "press", "say": "And then?"}
    body.update(kw)
    return json.dumps(body)


def test_accept_without_a_named_rubric_point_is_coerced_to_press():
    """A model will accept a non-answer politely all day.

    Letting the candidate off the hook has to cost the interviewer something:
    it must name which rubric bullet the answer satisfied. An accept with an
    empty `covered` is the shape of sycophancy, so it is refused in code rather
    than discouraged in the prompt.
    """
    decision = parse_turn(_decision(verdict="accept", covered=[], say="Great, next."))
    assert decision.verdict == "press"


def test_accept_with_a_named_point_is_honoured():
    decision = parse_turn(
        _decision(verdict="accept", covered=["Names retrieval first"], say="Next.")
    )
    assert decision.verdict == "accept"


def test_empty_say_is_a_hard_error():
    """Never ship a silent interviewer."""
    with pytest.raises(ParseError):
        parse_turn(_decision(say="   "))


def test_press_does_not_advance_the_question():
    session = LiveSession(plan=PLAN)
    start = session.question_index
    session.apply(TurnDecision(covered=[], missing=["x"], verdict="press", say="?"))
    assert session.question_index == start


def test_two_presses_then_the_question_is_forced_forward():
    """A live session cannot stall on one question.

    Twenty minutes is the whole budget, and a model that keeps finding one more
    thing to probe will spend all of it on question one.
    """
    session = LiveSession(plan=PLAN)
    for _ in range(MAX_PRESSES):
        session.apply(TurnDecision(covered=[], missing=["x"], verdict="press", say="?"))
        assert session.question_index == 0
    session.apply(TurnDecision(covered=[], missing=["x"], verdict="press", say="?"))
    assert session.question_index == 1, "third press must advance anyway"
    assert session.presses == 0, "press budget resets on the new question"


def test_accept_advances_and_resets_the_press_budget():
    session = LiveSession(plan=PLAN)
    session.apply(TurnDecision(covered=[], missing=["x"], verdict="press", say="?"))
    session.apply(
        TurnDecision(covered=["ok"], missing=[], verdict="accept", say="Next")
    )
    assert session.question_index == 1
    assert session.presses == 0


def test_session_ends_after_the_last_question():
    session = LiveSession(plan=PLAN)
    for _ in range(len(PLAN["cards"])):
        session.apply(
            TurnDecision(covered=["ok"], missing=[], verdict="accept", say="Next")
        )
    assert session.finished


def test_turn_budget_stops_a_session_that_will_not_end():
    session = LiveSession(plan=PLAN, max_turns=3)
    for _ in range(3):
        assert not session.finished
        session.apply(TurnDecision(covered=[], missing=["x"], verdict="press", say="?"))
    assert session.finished, "the turn budget is a hard stop, not a suggestion"


def test_asked_reports_only_the_questions_actually_reached():
    """The verdict covers what was asked and nothing else.

    Grading a candidate on a question the session never got to is the easiest
    way to produce a confident, wrong summary.
    """
    session = LiveSession(plan=PLAN)
    session.apply(
        TurnDecision(covered=["ok"], missing=[], verdict="accept", say="Next")
    )
    assert session.asked() == [PLAN["cards"][0]["q"]]


def test_malformed_json_names_what_arrived():
    with pytest.raises(ParseError) as exc:
        parse_turn("the model went for a walk")
    assert "chars" in str(exc.value)
