from __future__ import annotations

from collections import Counter
from pathlib import Path

from .state import State, slug


def _coverage(state: State, syllabus: list[dict]):
    slug_to_nicho = {slug(i["topic"]): i["nicho"] for i in syllabus}
    totals = Counter(i["nicho"] for i in syllabus)
    done_by = Counter()
    failed_by = Counter()
    for entry in state.done:
        is_failed = entry.startswith("__failed__:")
        s = entry.removeprefix("__failed__:")
        nicho = slug_to_nicho.get(s)
        # done slugs no longer in the syllabus (renamed/removed) are intentionally
        # skipped: the syllabus is the authoritative denominator for coverage.
        if nicho is None:
            continue
        if is_failed:
            failed_by[nicho] += 1
        else:
            done_by[nicho] += 1
    return totals, done_by, failed_by


def render_status(state: State, syllabus: list[dict]) -> str:
    totals, done_by, failed_by = _coverage(state, syllabus)
    lines: list[str] = ["# SAGE Status", ""]

    lines += [
        "## Coverage",
        "",
        "| nicho | done | failed | remaining | total |",
        "|---|---|---|---|---|",
    ]
    for nicho in sorted(totals):
        total = totals[nicho]
        done = done_by.get(nicho, 0)
        failed = failed_by.get(nicho, 0)
        remaining = max(0, total - done - failed)
        lines.append(f"| {nicho} | {done} | {failed} | {remaining} | {total} |")
    lines.append("")

    lines += ["## Failures", ""]
    failed_entries = [e for e in state.done if e.startswith("__failed__:")]
    if not failed_entries:
        lines.append("None.")
    else:
        for e in failed_entries:
            s = e.removeprefix("__failed__:")
            info = state.failures.get(s)
            if info:
                lines.append(
                    f"- `{s}` - {info.get('reason', '?')} ({info.get('date', '?')})"
                )
            else:
                lines.append(f"- `{s}` - reason not recorded")
    lines.append("")

    lines += ["## Queue", "", f"{len(state.queue)} topic(s) pending."]
    for item in state.queue[:10]:
        lines.append(
            f"- {item.get('topic')} ({item.get('nicho')}, {item.get('source', '?')})"
        )
    lines.append("")

    u = state.usage
    lines += [
        "## Usage",
        "",
        f"- date: {u.get('date', '?')}",
        f"- writer calls: {u.get('writer_calls', 0)}",
        f"- critic calls: {u.get('critic_calls', 0)}",
        f"- tavily calls: {u.get('tavily_calls', 0)}",
        "",
    ]

    return "\n".join(lines)


def write_status(path: Path | str, state: State, syllabus: list[dict]) -> str:
    content = render_status(state, syllabus)
    Path(path).write_text(content, encoding="utf-8")
    return content
