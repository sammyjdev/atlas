from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

import yaml
from atlas_core.config import atlas_vault

from .anki import export as export_anki
from .jds import load_jds, pending_jds, prioritize_gaps
from .live import DEFAULT_MAX_TURNS, LiveSession, parse_turn
from .llm import LLMError, RateLimitError, writer_call
from .parser import ParseError
from .pipeline import run_interview, run_once
from .prompts import (
    LIVE_INTERVIEWER_SYSTEM,
    LIVE_INTERVIEWER_USER_TEMPLATE,
    LIVE_VERDICT_SYSTEM,
    LIVE_VERDICT_USER_TEMPLATE,
    format_plan_block,
    format_transcript,
)
from .state import State
from .state import load as load_state
from .state import save as save_state
from .status import write_status
from .syllabus import find_gaps, load_syllabus
from .track import SCREENING, TECHNICAL, Track
from .vault import append_turn, write_session_header


def state_path() -> Path:
    return atlas_vault() / "state.json"


def syllabus_path() -> Path:
    return atlas_vault() / "inputs" / "syllabus.yaml"


def jds_path() -> Path:
    return atlas_vault() / "inputs" / "jds"


def profile_path() -> Path:
    return atlas_vault() / "inputs" / "profile.md"


def _override(name: str) -> Path | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw).expanduser()


def vault_root() -> Path:
    return _override("SAGE_VAULT") or (atlas_vault() / "vault")


def apkg_path() -> Path:
    return _override("SAGE_APKG") or (atlas_vault() / "exports" / "sage.apkg")


def status_path() -> Path:
    return _override("SAGE_STATUS") or (atlas_vault() / "STATUS.md")


log = logging.getLogger("sage")


def refill_queue(state: State) -> None:
    if state.queue:
        return
    syllabus_file = syllabus_path()
    if not syllabus_file.exists():
        return
    syllabus = load_syllabus(syllabus_file)
    gaps = find_gaps(syllabus, state.done, state.queue)
    if not gaps:
        return
    jd_texts = load_jds(jds_path())
    today = date.today().isoformat()
    for item, source in prioritize_gaps(gaps, jd_texts):
        state.queue.append(
            {
                "topic": item["topic"],
                "nicho": item["nicho"],
                "source": source,
                "added": today,
            }
        )


def reset_usage_if_new_day(state: State) -> None:
    today = date.today().isoformat()
    if state.usage.get("date") != today:
        state.usage = {
            "date": today,
            "writer_calls": 0,
            "critic_calls": 0,
            "tavily_calls": 0,
        }


def _do_status(state: State) -> None:
    syllabus_file = syllabus_path()
    syllabus = load_syllabus(syllabus_file) if syllabus_file.exists() else []
    out = status_path()
    write_status(out, state, syllabus)
    log.info("status written to %s", out)


def _do_interview(state: State, vault: Path, track: Track = TECHNICAL) -> dict | None:
    """One pending JD, one interview, on the requested track.

    Session-driven, never the cron (see CLAUDE.md): it consumes whatever JD files
    are sitting in inputs/jds/ and stops after one.

    Pending is computed per track, so a posting whose technical interview is
    already done is still pending for screening. The two are different
    conversations about the same job.
    """
    profile = profile_path()
    if not profile.exists():
        log.error("no profile at %s - adversarial mode needs it", profile)
        return None
    jobs = jds_path()
    pending = pending_jds(jobs, state.done, key_prefix=track.key_prefix)
    if not pending:
        log.info("no pending JD in %s for track %s", jobs, track.name)
        return None
    jd_slug, jd_text = pending[0]
    log.info("%s: %s", track.name, jd_slug)
    return run_interview(
        state=state,
        profile=profile.read_text(encoding="utf-8"),
        jd=jd_text,
        jd_slug=jd_slug,
        vault_root=vault,
        today=date.today().isoformat(),
        track=track,
    )


def _load_plan(vault: Path, nicho: str, slug: str) -> dict | None:
    """Read a generated interview as the agenda for a live session."""
    path = vault / nicho / f"{slug}.md"
    if not path.exists():
        log.error("no plan at %s - generate it with --interview first", path)
        return None
    m = re.match(r"^---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.DOTALL)
    if not m:
        log.error("%s has no frontmatter", path)
        return None
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        log.error("%s: %s", path, e)
        return None


def _do_live(vault: Path, slug: str, track: Track, max_turns: int) -> int:
    """Conduct the interview in the terminal, one question at a time.

    Session-driven and never reachable from the cron, for the same reason
    job-fit is not: there is a human in it.

    The plan is read off disk, so the session opens with no model call. A cold
    start would cost a writer+critic pass and about ninety seconds of measured
    silence, which is not a way to open an interview.
    """
    plan = _load_plan(vault, track.nicho, slug)
    if not plan:
        return 1
    session = LiveSession(plan=plan, max_turns=max_turns)
    if not session.cards:
        log.error("plan has no questions")
        return 1

    profile = profile_path().read_text(encoding="utf-8")
    plan_block = format_plan_block(session.cards)
    title = plan.get("vaga") or slug
    path = write_session_header(
        root=vault,
        nicho=track.nicho,
        slug=slug,
        title=title,
        created=date.today().isoformat(),
    )

    opening = str(session.cards[0].get("q", "")).strip()
    print(f"\n{title}\n{'-' * len(title)}\n")
    print(f"Interviewer: {opening}\n")
    session.record("interviewer", opening)
    append_turn(path, "interviewer", opening)

    while not session.finished:
        try:
            answer = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not answer:
            continue
        session.record("candidate", answer)
        append_turn(path, "candidate", answer)

        card = session.current_card()
        if card is None:
            break
        started = time.monotonic()
        raw = writer_call(
            LIVE_INTERVIEWER_SYSTEM,
            LIVE_INTERVIEWER_USER_TEMPLATE.format(
                profile=profile,
                plan_block=plan_block,
                transcript=format_transcript(session.turns),
                index=session.question_index + 1,
                question=str(card.get("q", "")),
                rubric=str(card.get("a", "")),
            ),
        )
        elapsed = time.monotonic() - started
        try:
            decision = parse_turn(raw)
        except ParseError as e:
            log.error("turn unusable: %s", e)
            break
        session.apply(decision)
        append_turn(path, "interviewer", decision.say)
        # Per-turn wall clock, printed from the first run. Nothing else in this
        # repo measures it, and it is what decides whether a reasoning model can
        # hold a live conversation at all.
        print(f"\nInterviewer: {decision.say}\n   [{elapsed:.1f}s]\n")

    if session.asked():
        verdict = writer_call(
            LIVE_VERDICT_SYSTEM,
            LIVE_VERDICT_USER_TEMPLATE.format(
                asked="\n".join(f"- {q}" for q in session.asked()),
                transcript=format_transcript(session.turns),
            ),
        )
        with path.open("a", encoding="utf-8") as fh:
            fh.write("\n" + verdict.strip() + "\n")
        print(f"\n{verdict.strip()}\n")
    print(f"transcript: {path}")
    return 0


def _report_dry_run(vault: Path, result: dict | None) -> None:
    """Show what the run produced, since nothing was kept.

    A rejection is as informative as an approval here - the reason string now
    carries the offending output's length and tail, which is what tells a
    truncated response from a malformed one.
    """
    print(f"\nstatus: {(result or {}).get('status', 'nothing ran')}")
    if result and result.get("reason"):
        print(f"reason: {result['reason']}")
    for issue in (result or {}).get("issues", []):
        print(f"  - {issue.get('location', '?')}: {issue.get('problem', '')}")

    for path in sorted(vault.rglob("*.md")):
        if path.name.endswith(("-qa.md", "-voice.md")):
            continue
        m = re.match(r"^---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.DOTALL)
        if not m:
            continue
        try:
            cards = (yaml.safe_load(m.group(1)) or {}).get("cards") or []
        except yaml.YAMLError:
            continue
        print(f"\n{path.name}  ({len(cards)} questions)")
        for i, card in enumerate(cards, 1):
            if isinstance(card, dict) and card.get("q"):
                print(f"  {i:2d}. {str(card['q'])[:140]}")

    print(f"\ndry run: nothing persisted. Output kept at {vault}")


def _do_export(vault: Path, out: Path) -> None:
    if not vault.exists():
        log.info("vault %s does not exist yet — nothing to export", vault)
        return
    counts = export_anki(vault, out)
    total = sum(counts.values())
    log.info("anki export: %s (%d cards) → %s", counts, total, out)


def cli() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="run one topic and exit")
    parser.add_argument(
        "--export-only", action="store_true", help="skip pipeline, only rebuild .apkg"
    )
    parser.add_argument(
        "--no-export", action="store_true", help="skip .apkg export after run"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="regenerate STATUS.md from current state and exit",
    )
    parser.add_argument(
        "--interview",
        action="store_true",
        help="adversarial mode: hard questions for one pending JD in inputs/jds/",
    )
    parser.add_argument(
        "--screening",
        action="store_true",
        help="HR screening track instead of the technical one: same posting, "
        "a recruiter's questions and a rubric that grades positioning",
    )
    parser.add_argument(
        "--live",
        metavar="SLUG",
        help="conduct the interview for a generated plan, one question at a "
        "time, in this terminal. Never runs in CI: there is a human in it",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=DEFAULT_MAX_TURNS,
        help=f"hard stop on a live session (default {DEFAULT_MAX_TURNS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="real models, no footprint: writes to a throwaway vault and "
        "persists neither state.json, STATUS.md nor the .apkg",
    )
    args = parser.parse_args()

    try:
        atlas_vault()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    vault = vault_root()
    apkg = apkg_path()

    # A dry run makes the real calls and throws the results away. The point is
    # validating a change against the live models without paying for it in
    # state: a failed run costs a __failed__ entry and two of the three retries
    # a slug gets, and the last batch burned six of its sixteen slots that way.
    #
    # Redirecting the vault covers the pipeline. --status and --export-only
    # write STATUS.md and the .apkg on their own, so those branches must
    # return before the write when this flag is set.
    if args.dry_run:
        vault = Path(tempfile.mkdtemp(prefix="sage-dry-run-"))
        log.info("dry run: vault redirected to %s, nothing will be persisted", vault)

    if args.export_only:
        if not args.dry_run:
            _do_export(vault, apkg)
        return 0

    if args.status:
        if not args.dry_run:
            state = load_state(state_path())
            _do_status(state)
        return 0

    if args.live:
        return _do_live(
            vault, args.live, SCREENING if args.screening else TECHNICAL, args.turns
        )

    state = load_state(state_path())
    reset_usage_if_new_day(state)
    if not args.interview:
        refill_queue(state)

    def persist() -> None:
        if args.dry_run:
            return
        save_state(state_path(), state)

    result = None
    try:
        if args.interview:
            result = _do_interview(
                state, vault, SCREENING if args.screening else TECHNICAL
            )
        else:
            result = run_once(
                state=state, vault_root=vault, today=date.today().isoformat()
            )
        log.info("result: %s", result)
    except RateLimitError as e:
        log.warning("rate limited: %s — exiting clean", e)
        persist()
        return 0
    except LLMError as e:
        log.error("llm error: %s — exiting clean for retry next run", e)
        persist()
        return 0
    except Exception as e:
        log.exception("unexpected: %s — exiting clean", e)
        persist()
        return 0

    if args.dry_run:
        _report_dry_run(vault, result)
        return 0

    persist()
    _do_status(state)

    if not args.no_export and result and result.get("status") == "approved":
        try:
            _do_export(vault, apkg)
        except Exception as e:
            log.exception("anki export failed: %s", e)

    return 0


if __name__ == "__main__":
    sys.exit(cli())
