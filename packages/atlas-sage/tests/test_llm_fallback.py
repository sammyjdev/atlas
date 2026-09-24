import pytest

from atlas_sage import llm


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload or "")
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


def _ok(content: str) -> FakeResponse:
    return FakeResponse(200, {"choices": [{"message": {"content": content}}]})


def test_critic_uses_openrouter_when_ok(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(url)
        return _ok("primary response")

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "g")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "n")
    result = llm.critic_call("sys", "user")
    assert result == "primary response"
    assert calls == [llm.OPENROUTER_URL]


def test_critic_falls_back_to_deepinfra_on_429(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(url)
        if "openrouter.ai" in url:
            return FakeResponse(429, text="rate limited")
        return _ok("fallback response")

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "g")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "n")
    result = llm.critic_call("sys", "user")
    assert result == "fallback response"
    assert calls == [llm.OPENROUTER_URL, llm.DEEPINFRA_URL]


def test_critic_falls_back_on_5xx(monkeypatch):
    def fake_post(url, headers, json, timeout):
        if "openrouter.ai" in url:
            return FakeResponse(503, text="upstream down")
        return _ok("fallback")

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "g")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "n")
    assert llm.critic_call("sys", "user") == "fallback"


def test_critic_no_fallback_without_deepinfra_key(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return FakeResponse(429, text="rate limited")

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "g")
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    with pytest.raises(llm.RateLimitError):
        llm.critic_call("sys", "user")


def test_writer_uses_openrouter_when_ok(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(url)
        return _ok("primary writer")

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "g")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "n")
    assert llm.writer_call("sys", "user") == "primary writer"
    assert calls == [llm.OPENROUTER_URL]


def test_writer_falls_back_to_deepinfra_on_429(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(url)
        if "openrouter.ai" in url:
            return FakeResponse(429, text="rate limited")
        return _ok("deepinfra writer")

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "g")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "n")
    assert llm.writer_call("sys", "user") == "deepinfra writer"
    assert calls == [llm.OPENROUTER_URL, llm.DEEPINFRA_URL]


def test_writer_no_fallback_without_deepinfra_key(monkeypatch):
    monkeypatch.setattr(
        llm.requests,
        "post",
        lambda url, headers, json, timeout: FakeResponse(429, text="tpd"),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "g")
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    with pytest.raises(llm.RateLimitError):
        llm.writer_call("sys", "user")


def test_writer_uses_low_temperature(monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["temperature"] = json["temperature"]
        return _ok("ok")

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "g")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "n")
    llm.writer_call("sys", "user")
    assert captured["temperature"] == 0.1


def test_critic_has_its_own_output_budget(monkeypatch):
    """The critic's budget is separate from the writer's, and both ends bite.

    Too small truncates the JSON mid-issue, which surfaces as a parse error rather
    than a limit error and is much harder to diagnose (a 5-issue verdict measured
    ~650 tokens). Too large means the critic inherits the writer's ceiling, which
    on a metered model is paying document prices for a three-field JSON.
    """
    from atlas_sage import llm

    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(json)

        class R:
            status_code = 200
            ok = True

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": "{}"}}]}

        return R()

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")

    llm.critic_call("sys", "user")
    budget = seen["max_tokens"]
    assert budget >= 1000, f"critic budget truncates a 5-issue verdict: {budget}"
    assert budget < llm.WRITER_MAX_TOKENS, "critic must not claim the writer's budget"


def test_writer_keeps_the_full_document_budget(monkeypatch):
    from atlas_sage import llm

    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(json)

        class R:
            status_code = 200
            ok = True

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": "ok response"}}]}

        return R()

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")

    llm.writer_call("sys", "user")
    assert seen["max_tokens"] >= 4000, "writer must still fit a full document"


def test_empty_content_fails_loudly_instead_of_returning_none(monkeypatch):
    """A reasoning model that spends its budget thinking returns content: null.

    Returning that None propagated to parse_critic_output and surfaced as
    "'NoneType' object has no attribute 'find'", which says nothing about the
    cause. The failure must name it at the source.
    """

    def fake_post(url, headers=None, json=None, timeout=None):
        class R:
            status_code = 200
            ok = True
            text = ""

            @staticmethod
            def json():
                return {
                    "choices": [
                        {"message": {"content": None, "reasoning": "thinking..."}}
                    ]
                }

        return R()

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)

    with pytest.raises(llm.LLMError, match="empty content"):
        llm.critic_call("sys", "user")


def test_single_char_content_fails_loudly_like_empty_content(monkeypatch):
    """A reasoning model that spends its budget thinking returns almost nothing usable.

    A 1-char response passes the empty-content guard but fails in the parser as
    `writer_parse: missing YAML frontmatter [got 1 chars, ends: ...'']`. The root cause
    is the same as empty content, so it must be caught and named here.
    """

    def fake_post(url, headers=None, json=None, timeout=None):
        class R:
            status_code = 200
            ok = True
            text = ""

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": "-", "reasoning": None}}]}

        return R()

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)

    with pytest.raises(llm.LLMError, match="empty content"):
        llm.writer_call("sys", "user")


def test_critic_bounds_its_reasoning_like_the_writer(monkeypatch):
    """Both roles run reasoning models; neither may spend the budget thinking."""
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(json)

        class R:
            status_code = 200
            ok = True

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": "{}"}}]}

        return R()

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    llm.critic_call("sys", "user")
    assert "reasoning" in seen, "critic must bound reasoning effort too"
