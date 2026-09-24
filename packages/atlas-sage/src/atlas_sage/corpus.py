"""A corpus of published interview questions, used as a measurement baseline.

It was built to be a negative filter, and that did not survive measurement. A
leave-one-family-out hold-out put lexical overlap at 5.5% recall against a source
that never fed the corpus (n=2500), and no threshold rescued it: at the setting
that reaches 70% recall the same rule rejects 86% of what SAGE generates. Recall
and false positives move together because a situated question reuses the domain
nouns of the recitable one - the two differ in FORM, not in vocabulary, so no
amount of lexical or semantic similarity separates them. Embeddings were the
obvious next reach and would inherit the same failure, since "What is RAG?" and
"your RAG pipeline returns stale chunks after a reindex" are neighbours in any
topical space.

The gate the filter wanted to be already exists: the interview writer is told
never to ask what a definition answers, and the interview critic rejects anything
a bluffer could recite. Measured on SAGE's own output, 0 of 21 questions were
definitional.

So the corpus stays with its role inverted. It is not a filter in the hot path;
it is the baseline that makes the critic auditable - the reference population
against which "SAGE does not generate recitable questions" is a claim with a
number behind it rather than an assertion.

Licence is enforced here rather than documented: a source whose SPDX id is not
permissive is refused before a single byte is harvested. This corpus is meant to
back a product, and a product built on questionably-licensed data has the problem
in its main asset.
"""

from __future__ import annotations

import re
from collections import defaultdict
from enum import Enum

# SPDX ids that permit redistribution and commercial use. Deliberately a short
# allowlist: anything absent (GPL, AGPL, NC variants, NOASSERTION, unlicensed)
# is refused rather than reasoned about.
ALLOWED_LICENSES = frozenset(
    {"mit", "apache-2.0", "cc0-1.0", "bsd-2-clause", "bsd-3-clause", "unlicense"}
)

# Presence, not recurrence, is the recitability signal.
#
# The first real harvest falsified the original design. Across 13 repos in 11
# editorial families, 3352 distinct questions produced only 27 that appeared in
# two or more families - 99.2% were unique to one source. Repositories do not
# copy each other's phrasing; they each write the same idea their own way.
#
# But a question does not need to recur to be recitable: if it sits in ONE public
# repo with thousands of stars, every candidate has already read it. So the corpus
# is every harvested question, and the default threshold is 1. Keeping the knob
# because a stricter corpus is still useful for measuring how common a topic is,
# as opposed to how public a phrasing is.
MIN_SOURCES_FOR_COMMON = 1

# Document boilerplate that happens to end in "?". Found empirically: "## What is
# this?" topped the first real harvest because three repos share the same README
# heading, which says nothing about interview questions.
_BOILERPLATE = re.compile(
    r"^(what is this|why|how|what|who|when|where|how to use|how does it work|"
    r"what.s inside|table of contents|faq|questions?)\W*$",
    re.I,
)

# An interview question carries a subject. Anything shorter is a heading.
MIN_QUESTION_WORDS = 4

# Fraction of a question's LETTERS that must be ASCII.
#
# Normalization strips everything outside [a-z0-9], which silently turns a
# non-Latin question into a stub: '.Net의 개체 풀이란 무엇입니까?' has four words
# and normalizes to the single token 'net'. 227 such entries entered the first
# harvest and then matched every candidate containing their one surviving token,
# enough to inflate the filter's apparent recall by 3.6x.
#
# Two calibrations that did not work, both measured against the real corpus:
# a word floor throws away "What is React?" (three words, and the most recitable
# question there is), and a fraction of surviving WORDS leaks 27 entries because
# Korean agglutinates its particle onto the Latin term - 'ArrayList와' normalizes
# to 'arraylist', landing the ratio exactly on 0.5. Letters are the granularity
# that separates cleanly: at 0.8 the rule drops 0 English questions out of 3953
# and keeps only 4 foreign ones out of 227.
MIN_ASCII_LETTER_FRACTION = 0.8

# Translated copies are excluded by path, before a byte is fetched.
#
# These repos ship the same handbook in a dozen languages and the harvest took
# every .md it found. That put 227 non-Latin questions and 158 Portuguese,
# Spanish and Polish ones into a corpus whose every downstream rule assumes
# English - and counted one question translated five times as five distinct
# questions, inflating the very recurrence the corpus was built to measure.
#
# Path, not content: a Portuguese question is almost pure ASCII, so no character
# rule can find it after the fact. The directory name can, for free.
_LANG = (
    "ar|bg|bn|cs|da|de|el|es|fa|fi|fr|he|hi|hu|id|it|ja|ko|nl|no|pl|pt|pt-br|"
    "ro|ru|sv|th|tr|uk|ur|vi|zh|zh-cn|zh-tw"
)
_TRANSLATION_PATH = re.compile(
    rf"(^|/)(i18n|translations?|locales?|lang)(/|$)"
    rf"|(^|/)({_LANG})(/|$)"
    rf"|\.({_LANG})\.(md|json)$",
    re.I,
)

_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_LIST_PREFIX = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_MARKUP = re.compile(r"[*_`#>\[\]()]")
_NON_WORD = re.compile(r"[^a-z0-9\s]")
_SPACES = re.compile(r"\s+")


class LicenseStatus(Enum):
    """Why a source was or was not cleared.

    ABSENT and UNVERIFIABLE both block harvesting, but they are different facts
    about the world and must not be reported as one. A rate-limited API once
    produced thirteen "this repo has no licence" verdicts for thirteen repos that
    are all correctly licensed - the decision was right, the stated reason was a
    fabrication.
    """

    ALLOWED = "allowed"
    REFUSED = "refused"  # licence present, not on the allowlist
    ABSENT = "absent"  # API answered: no licence declared
    UNVERIFIABLE = "unverifiable"  # API did not answer

    @property
    def may_harvest(self) -> bool:
        return self is LicenseStatus.ALLOWED


def classify_license(spdx: str | None, error: str | None = None) -> LicenseStatus:
    if error:
        return LicenseStatus.UNVERIFIABLE
    if not spdx or spdx.strip().upper() == "NOASSERTION":
        return LicenseStatus.ABSENT
    if spdx.strip().lower() in ALLOWED_LICENSES:
        return LicenseStatus.ALLOWED
    return LicenseStatus.REFUSED


def license_allows_reuse(spdx: str | None) -> bool:
    """True only for an explicitly permissive SPDX id."""
    if not spdx:
        return False
    return spdx.strip().lower() in ALLOWED_LICENSES


def normalize_question(text: str) -> str:
    """Collapse cosmetic differences so the same question hashes the same.

    Two repositories writing "1. What is React?" and "**what is react**" must
    land on one key, or recurrence counts formatting instead of content.
    """
    out = _LIST_PREFIX.sub("", text.strip())
    out = _MARKUP.sub(" ", out)
    out = _NON_WORD.sub(" ", out.lower())
    return _SPACES.sub(" ", out).strip()


def is_translation(path: str) -> bool:
    """True for a repo path that carries a language tag as a directory or suffix."""
    return bool(_TRANSLATION_PATH.search(path))


def survives_normalization(text: str) -> bool:
    """False when normalization would leave a stub rather than the question.

    The corpus is English; a question in another script normalizes to whatever
    Latin tokens happen to be embedded in it, which is not the question. This is
    the net under the harvest, not the main defence - translated files are
    excluded by path before they are ever fetched. It still earns its place,
    because a repo can put a translation anywhere.
    """
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    ascii_letters = sum(1 for c in letters if c.isascii())
    return ascii_letters / len(letters) >= MIN_ASCII_LETTER_FRACTION


def extract_questions(markdown: str) -> list[str]:
    """Pull interrogative lines out of a markdown document.

    Code fences are stripped first: a `# What is this?` comment inside a snippet
    is not an interview question, and counting it would poison the corpus with
    whatever the example code happens to say.
    """
    body = _CODE_FENCE.sub("", markdown)
    found: list[str] = []
    for raw in body.splitlines():
        line = _LIST_PREFIX.sub("", raw.strip())
        line = line.lstrip("#").strip()
        line = line.strip("*_` ")
        if not line or len(line) < 10:
            continue
        if _BOILERPLATE.match(line):
            continue
        if len(line.split()) < MIN_QUESTION_WORDS:
            continue
        if not survives_normalization(line):
            continue
        if line.endswith("?") or re.match(r"^(explain|describe|define)\b", line, re.I):
            found.append(line)
    return found


def extract_questions_from_json(payload: str) -> list[str]:
    """Pull questions out of JSON sources.

    Three sources returned zero questions in the first harvest because their
    content is JSON, not markdown. Walks the structure rather than assuming a
    shape, since every repo names the field differently.
    """
    import json

    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        return []

    found: list[str] = []
    fields = {"question", "q", "prompt", "text"}

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key.lower() in fields and isinstance(value, str) and value.strip():
                    found.append(value.strip())
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return found


def rank_by_recurrence(harvested: list[tuple[str, str]]) -> list[dict]:
    """Rank normalized questions by how many DISTINCT sources carry them.

    Distinct sources, not occurrences: a question repeated fifty times inside one
    repository says nothing about how common it is in the wild.
    """
    seen: dict[str, set[str]] = defaultdict(set)
    original: dict[str, str] = {}
    for source, text in harvested:
        key = normalize_question(text)
        if not key or not survives_normalization(text):
            continue
        seen[key].add(source)
        original.setdefault(key, text.strip())

    rows = [
        {
            "question": key,
            "original": original[key],
            "sources": len(sources),
            "seen_in": sorted(sources),
        }
        for key, sources in seen.items()
    ]
    rows.sort(key=lambda r: (-r["sources"], r["question"]))
    return rows


def rank_by_recurrence_by_family(
    harvested: list[tuple[str, str]], families: dict[str, str]
) -> list[dict]:
    """Rank by DISTINCT EDITORIAL FAMILIES, keeping repos for provenance.

    Counting repositories overstates recurrence whenever several of them share an
    origin: one author publishing an LLM hub and a RAG hub is one editorial voice,
    and a translated fork is the same list in another language. Since recurrence
    is the whole basis of the recitability signal, inflating it here would quietly
    inflate every downstream claim.

    A repo with no mapping is its own family, so an unaudited source can never be
    silently merged into another.
    """
    by_family: dict[str, set[str]] = defaultdict(set)
    by_repo: dict[str, set[str]] = defaultdict(set)
    original: dict[str, str] = {}

    for repo, text in harvested:
        key = normalize_question(text)
        if not key or not survives_normalization(text):
            continue
        by_family[key].add(families.get(repo, repo))
        by_repo[key].add(repo)
        original.setdefault(key, text.strip())

    rows = [
        {
            "question": key,
            "original": original[key],
            "sources": len(fams),
            "families": sorted(fams),
            "seen_in": sorted(by_repo[key]),
        }
        for key, fams in by_family.items()
    ]
    rows.sort(key=lambda r: (-r["sources"], r["question"]))
    return rows
