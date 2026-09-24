"""The two interview tracks, as data rather than as two copies of the pipeline.

A technical interview and a screening call are the same machinery pointed at a
different rubric: draft, parse, judge, one bounded revision, write. What differs
is which prompts the writer and critic get, and where the result lands.

They cannot share a rubric. The technical critic rejects anything a bluffer
could answer and demands a number, a named alternative or a consequence; a good
screening question ("which ONE project are you proudest of?") has none of those
and would be rejected outright. So the rubric is the parameter, and everything
around it stays one implementation.
"""

from __future__ import annotations

from typing import NamedTuple

from .prompts import (
    INTERVIEW_CRITIC_SYSTEM,
    INTERVIEW_CRITIC_USER_TEMPLATE,
    INTERVIEW_REVISE_USER_TEMPLATE,
    INTERVIEW_WRITER_SYSTEM,
    INTERVIEW_WRITER_USER_TEMPLATE,
    SCREENING_CRITIC_SYSTEM,
    SCREENING_CRITIC_USER_TEMPLATE,
    SCREENING_REVISE_USER_TEMPLATE,
    SCREENING_WRITER_SYSTEM,
    SCREENING_WRITER_USER_TEMPLATE,
)


class Track(NamedTuple):
    """One interview track.

    `key_prefix` keeps the tracks from blocking each other in state: the same
    posting produces both a technical call and a screening call, and a shared
    key would let whichever ran first mark the posting done for both.

    `nicho` keeps them apart on disk, and that separation is load-bearing rather
    than tidy. Three consumers glob the interview directory and skip only
    "-qa.md" and "-voice.md": the Anki export, the label sheet a recruiter fills
    in for TECHNICAL question quality, and the recitability measurement whose
    baseline is a published number. A screening document in that directory would
    be swept into all three and scored by rules written for the other track. A
    filename suffix would not have stopped it; a directory does, because
    anki.export skips a nicho with no deck id and both scripts glob one level.
    """

    name: str
    key_prefix: str
    nicho: str
    writer_system: str
    writer_template: str
    critic_system: str
    critic_template: str
    revise_template: str

    def key(self, jd_slug: str) -> str:
        return f"{self.key_prefix}:{jd_slug}"


TECHNICAL = Track(
    name="technical",
    key_prefix="interview",
    nicho="interview",
    writer_system=INTERVIEW_WRITER_SYSTEM,
    writer_template=INTERVIEW_WRITER_USER_TEMPLATE,
    critic_system=INTERVIEW_CRITIC_SYSTEM,
    critic_template=INTERVIEW_CRITIC_USER_TEMPLATE,
    revise_template=INTERVIEW_REVISE_USER_TEMPLATE,
)

SCREENING = Track(
    name="screening",
    key_prefix="screening",
    nicho="screening",
    writer_system=SCREENING_WRITER_SYSTEM,
    writer_template=SCREENING_WRITER_USER_TEMPLATE,
    critic_system=SCREENING_CRITIC_SYSTEM,
    critic_template=SCREENING_CRITIC_USER_TEMPLATE,
    revise_template=SCREENING_REVISE_USER_TEMPLATE,
)

TRACKS = {t.name: t for t in (TECHNICAL, SCREENING)}
