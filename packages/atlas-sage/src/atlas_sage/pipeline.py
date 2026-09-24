from __future__ import annotations

import os
from pathlib import Path

from .llm import critic_call, writer_call
from .parser import (
    ParseError,
    parse_critic_output,
    parse_interview_output,
    parse_writer_output,
)
from .prompts import (
    CRITIC_SYSTEM,
    CRITIC_USER_TEMPLATE,
    REVISE_USER_TEMPLATE,
    WRITER_SYSTEM,
    WRITER_USER_TEMPLATE,
    format_sources,
)
from .search import MIN_SOURCES, search
from .state import State, record_done, record_failed, record_retry, slug
from .track import TECHNICAL, Track
from .vault import write_entry, write_qa, write_voice_prompt


def run_once(state: State, vault_root: Path, today: str) -> dict:
    if not state.queue:
        return {"status": "idle"}

    item = state.queue[0]
    topic = item["topic"]
    nicho = item["nicho"]
    s = slug(topic)

    sources = search(topic, nicho, os.environ["TAVILY_API_KEY"])
    state.usage["tavily_calls"] = state.usage.get("tavily_calls", 0) + 1

    if len(sources) < MIN_SOURCES:
        # not enough whitelisted sources → permanent skip
        record_failed(state, s, "no_quality_sources")
        return {"status": "failed", "slug": s, "reason": "no_quality_sources"}

    sources_block = format_sources(sources)

    writer_user = WRITER_USER_TEMPLATE.format(
        topic=topic, nicho=nicho, sources_block=sources_block
    )
    writer_raw = writer_call(WRITER_SYSTEM, writer_user)
    state.usage["writer_calls"] = state.usage.get("writer_calls", 0) + 1

    try:
        parsed = parse_writer_output(writer_raw)
    except ParseError as e:
        record_retry(state, s, reason=f"writer_parse: {e}")
        return {"status": "rejected", "slug": s, "reason": f"writer_parse: {e}"}

    critic_user = CRITIC_USER_TEMPLATE.format(
        sources_block=sources_block, writer_output=writer_raw, nicho=nicho
    )
    critic_raw = critic_call(CRITIC_SYSTEM, critic_user)
    state.usage["critic_calls"] = state.usage.get("critic_calls", 0) + 1

    try:
        critic = parse_critic_output(critic_raw)
    except ParseError as e:
        record_retry(state, s, reason=f"critic_parse: {e}")
        return {"status": "rejected", "slug": s, "reason": f"critic_parse: {e}"}

    if not critic.decision_accepts():
        # one bounded in-run revision: the writer sees the critic's issues and
        # produces a corrected draft, which the critic re-judges once.
        issues_text = "\n".join(
            f"- {i.get('location', '?')}: {i.get('problem', '')}" for i in critic.issues
        )
        revise_user = REVISE_USER_TEMPLATE.format(
            sources_block=sources_block,
            draft=writer_raw,
            issues=issues_text,
            nicho=nicho,
        )
        writer_raw = writer_call(WRITER_SYSTEM, revise_user)
        state.usage["writer_calls"] = state.usage.get("writer_calls", 0) + 1
        try:
            parsed = parse_writer_output(writer_raw)
        except ParseError as e:
            record_retry(state, s, reason=f"revise_parse: {e}")
            return {"status": "rejected", "slug": s, "reason": f"revise_parse: {e}"}
        critic_user = CRITIC_USER_TEMPLATE.format(
            sources_block=sources_block, writer_output=writer_raw, nicho=nicho
        )
        critic_raw = critic_call(CRITIC_SYSTEM, critic_user)
        state.usage["critic_calls"] = state.usage.get("critic_calls", 0) + 1
        try:
            critic = parse_critic_output(critic_raw)
        except ParseError as e:
            record_retry(state, s, reason=f"critic_parse: {e}")
            return {"status": "rejected", "slug": s, "reason": f"critic_parse: {e}"}

    if not critic.decision_accepts():
        record_retry(state, s, reason="critic")
        return {
            "status": "rejected",
            "slug": s,
            "reason": "critic",
            "issues": critic.issues,
        }

    title = topic.strip().title() if topic == topic.lower() else topic.strip()
    write_entry(
        root=vault_root,
        nicho=nicho,
        slug=s,
        title=title,
        created=today,
        parsed=parsed,
        sources=sources,
    )
    write_qa(
        root=vault_root,
        nicho=nicho,
        slug=s,
        title=title,
        created=today,
        parsed=parsed,
    )
    record_done(state, s)
    return {"status": "approved", "slug": s}


def run_interview(
    state: State,
    profile: str,
    jd: str,
    jd_slug: str,
    vault_root: Path,
    today: str,
    track: Track = TECHNICAL,
) -> dict:
    """Adversarial mode: one posting in, hard questions out.

    Same writer and critic as run_once, with the critic's polarity flipped: it
    rejects questions that are too EASY rather than drafts that are inaccurate.
    No Tavily call - the profile and the posting are the only sources.
    """
    key = track.key(jd_slug)
    if key in state.done or f"__failed__:{key}" in state.done:
        return {"status": "skipped", "slug": key}

    writer_user = track.writer_template.format(profile=profile, jd=jd)
    writer_raw = writer_call(track.writer_system, writer_user)
    state.usage["writer_calls"] = state.usage.get("writer_calls", 0) + 1

    try:
        parsed = parse_interview_output(writer_raw)
    except ParseError as e:
        record_retry(state, key, reason=f"writer_parse: {e}")
        return {"status": "rejected", "slug": key, "reason": f"writer_parse: {e}"}

    critic_user = track.critic_template.format(
        profile=profile, jd=jd, writer_output=writer_raw
    )
    critic_raw = critic_call(track.critic_system, critic_user)
    state.usage["critic_calls"] = state.usage.get("critic_calls", 0) + 1

    try:
        critic = parse_critic_output(critic_raw)
    except ParseError as e:
        record_retry(state, key, reason=f"critic_parse: {e}")
        return {"status": "rejected", "slug": key, "reason": f"critic_parse: {e}"}

    if not critic.decision_accepts():
        # One bounded revision, same shape as run_once: the writer sees why the
        # questions were too soft and sharpens them.
        issues_text = "\n".join(
            f"- {i.get('location', '?')}: {i.get('problem', '')}" for i in critic.issues
        )
        revise_user = track.revise_template.format(
            profile=profile, jd=jd, draft=writer_raw, issues=issues_text
        )
        writer_raw = writer_call(track.writer_system, revise_user)
        state.usage["writer_calls"] = state.usage.get("writer_calls", 0) + 1
        try:
            parsed = parse_interview_output(writer_raw)
        except ParseError as e:
            record_retry(state, key, reason=f"revise_parse: {e}")
            return {"status": "rejected", "slug": key, "reason": f"revise_parse: {e}"}
        critic_user = track.critic_template.format(
            profile=profile, jd=jd, writer_output=writer_raw
        )
        critic_raw = critic_call(track.critic_system, critic_user)
        state.usage["critic_calls"] = state.usage.get("critic_calls", 0) + 1
        try:
            critic = parse_critic_output(critic_raw)
        except ParseError as e:
            record_retry(state, key, reason=f"critic_parse: {e}")
            return {"status": "rejected", "slug": key, "reason": f"critic_parse: {e}"}

    if not critic.decision_accepts():
        record_retry(state, key, reason="critic_too_easy")
        return {
            "status": "rejected",
            "slug": key,
            "reason": "critic_too_easy",
            "issues": critic.issues,
        }

    title = parsed.get("vaga") or jd_slug
    write_entry(
        root=vault_root,
        nicho=track.nicho,
        slug=jd_slug,
        title=title,
        created=today,
        parsed=parsed,
    )
    write_qa(
        root=vault_root,
        nicho=track.nicho,
        slug=jd_slug,
        title=title,
        created=today,
        parsed=parsed,
    )
    write_voice_prompt(
        root=vault_root,
        nicho=track.nicho,
        slug=jd_slug,
        title=title,
        created=today,
        parsed=parsed,
    )
    record_done(state, key)
    return {"status": "approved", "slug": key}
