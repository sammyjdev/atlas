from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger("sage.llm")


class LLMError(Exception):
    pass


class RateLimitError(LLMError):
    pass


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEEPINFRA_URL = "https://api.deepinfra.com/v1/openai/chat/completions"

# A 1-char response is unusable content and the same failure mode as empty: a
# reasoning model spent its whole budget thinking. One interview died as
# `writer_parse: missing YAML frontmatter [got 1 chars, ends: ...'']`, which
# names the parser rather than the cause.
#
# 2 and not higher because _chat is shared with the critic, whose smallest
# legitimate response is `{}`. A larger floor would start rejecting real
# verdicts, and this guard must only ever fire on nothing.
MIN_CONTENT_CHARS = 2

# Paid inference on OpenRouter, with DeepInfra serving the SAME two models as
# fallback - so a provider outage changes the route, never the behaviour.
#
# Why paid: the free tiers could not carry the adversarial interview mode. Groq
# retired every text-generation Llama, then capped output at 1000 tokens/min on
# Qwen, input at 7000/min, and total at 8000/min, while that mode sends profile +
# posting + the full generated document to the critic. Measured cost here is
# ~$0.0008 per cycle, roughly 7 cents a month at 3 runs/day.
#
# Cross-family decorrelation is the reason a separate critic exists, and it is
# the one rule that survived every rewrite: DeepSeek writes, Mistral judges.
# groq/compound taught the sharp version of this lesson - it presents as its own
# family but routes to gpt-oss underneath, which a 429 inside critic_call
# revealed by naming the writer's model. A critic that is secretly the writer is
# worse than no critic, because it still reports a verdict.
#
# Chosen on the Artificial Analysis Intelligence Index v4.3 (read 2026-09-12)
# against real per-token price, NOT against the index's own cost-per-task: that
# metric rewards models that emit few tokens, and this workload emits a 4000-token
# document, so output price dominates. gpt-5.6-luna looks cheapest there ($0.04
# per task, index 38) and costs 12x more here at $1.20/1M output.
#
# Mistral Small was the first pick and was wrong: index 7 against the writer's 35.
# A judge weaker than the writer approves almost everything and still reports a
# verdict, which is worse than no critic at all.
#
# The judge is deliberately stronger than the writer: 42 against 35.
WRITER_MODEL = "deepseek/deepseek-v4-flash-0731"  # idx 35, $0.04/$0.08 per 1M
WRITER_FALLBACK_MODEL = "deepseek-ai/DeepSeek-V4-Flash-0731"
CRITIC_MODEL = "z-ai/glm-5.3-flash"  # idx 42, $0.15/$0.50 per 1M
CRITIC_FALLBACK_MODEL = "zai-org/GLM-5.3-Flash"

# Budget is per role because the roles differ by an order of magnitude: the writer
# emits a full document, the critic a capped 5-issue verdict.
#
# The writer's budget covers reasoning tokens too. DeepSeek V4 Flash is a
# reasoning model and reasoning shares the same budget as the answer, so a
# ceiling that only fits the document is spent thinking and returns nothing.
#
# 12000 was set from the AA index's "45k reasoning tokens at max effort" and the
# assumption that effort=low would stay far under it. Measured on a real batch,
# it does not: one interview logged a 51809-character reasoning field, roughly
# 13k tokens, against a 12000 ceiling. The whole budget went to reasoning, the
# writer returned empty content, and the fallback inherited the request.
#
# That was 3 of 16 interviews in one batch, and the same posting failed twice
# with DIFFERENT parse errors - the signature of truncation landing in a
# different place each time, not of a malformed document.
#
# 24000 covers the observed reasoning plus the ~4000-token document with margin.
# Reasoning bills as output at $0.08/1M, so the worst case is ~$0.002 per call.
WRITER_MAX_TOKENS = 24000
CRITIC_MAX_TOKENS = 2000
REASONING_EFFORT = "low"


def _chat(
    url: str,
    model: str,
    api_key: str,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int = WRITER_MAX_TOKENS,
    extra: dict | None = None,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if extra:
        body.update(extra)
    resp = requests.post(url, headers=headers, json=body, timeout=120)
    provider = "openrouter" if "openrouter.ai" in url else "deepinfra"
    if resp.status_code == 429:
        raise RateLimitError(f"429 from {provider}: {resp.text[:200]}")
    if resp.status_code >= 500:
        raise LLMError(f"{resp.status_code} from {provider}: {resp.text[:200]}")
    if not resp.ok:
        raise LLMError(f"{resp.status_code} from {provider}: {resp.text[:500]}")
    data = resp.json()
    message = data["choices"][0]["message"]
    content = message.get("content")
    if not content or len(content) < MIN_CONTENT_CHARS:
        # A reasoning model that spends its whole budget thinking returns
        # content: null with the thinking in `reasoning`. Returning that None
        # surfaces far downstream as an AttributeError in the parser, which says
        # nothing about the cause - so name it here instead.
        reasoning_len = len(message.get("reasoning") or "")
        raise LLMError(
            f"{model} returned empty content "
            f"(got {len(content or '')} chars, reasoning field: {reasoning_len} chars) - the token budget was "
            f"likely spent on reasoning; lower the effort or raise max_tokens"
        )
    return content


def writer_call(system: str, user: str) -> str:
    key = os.environ["OPENROUTER_API_KEY"]
    try:
        return _chat(
            OPENROUTER_URL,
            WRITER_MODEL,
            key,
            system,
            user,
            temperature=0.1,
            extra={"reasoning": {"effort": REASONING_EFFORT}},
        )
    except (RateLimitError, LLMError) as primary_err:
        fallback_key = os.environ.get("DEEPINFRA_API_KEY")
        if not fallback_key:
            raise
        log.warning(
            "writer primary failed (%s) — falling back to DeepInfra %s",
            primary_err,
            WRITER_FALLBACK_MODEL,
        )
        # ponytail: no reasoning control on this leg, so the route does change
        # the behaviour despite what the header above promises - the same
        # reasoning model runs at whatever effort DeepInfra defaults to. It
        # inherits the raised budget, which is what actually caused the observed
        # failure, so this is left alone until evidence says otherwise: the
        # parameter spelling differs from OpenRouter's and guessing it wrong
        # returns 400, which would break the fallback outright rather than
        # degrade it. Confirm against DeepInfra's docs before adding it.
        return _chat(
            DEEPINFRA_URL,
            WRITER_FALLBACK_MODEL,
            fallback_key,
            system,
            user,
            temperature=0.1,
        )


def critic_call(system: str, user: str) -> str:
    key = os.environ["OPENROUTER_API_KEY"]
    try:
        return _chat(
            OPENROUTER_URL,
            CRITIC_MODEL,
            key,
            system,
            user,
            temperature=0.0,
            max_tokens=CRITIC_MAX_TOKENS,
            extra={"reasoning": {"effort": REASONING_EFFORT}},
        )
    except (RateLimitError, LLMError) as primary_err:
        fallback_key = os.environ.get("DEEPINFRA_API_KEY")
        if not fallback_key:
            raise
        log.warning(
            "critic primary failed (%s) — falling back to DeepInfra %s",
            primary_err,
            CRITIC_FALLBACK_MODEL,
        )
        return _chat(
            DEEPINFRA_URL,
            CRITIC_FALLBACK_MODEL,
            fallback_key,
            system,
            user,
            temperature=0.0,
            max_tokens=CRITIC_MAX_TOKENS,
        )
