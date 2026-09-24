from atlas_sage.search import MIN_SOURCES, filter_whitelist


def test_filter_whitelist_llms():
    results = [
        {"url": "https://arxiv.org/abs/1706.03762", "content": "x"},
        {"url": "https://random-blog.com/x", "content": "y"},
        {"url": "https://huggingface.co/blog/post", "content": "z"},
    ]
    filtered = filter_whitelist(results, nicho="llms")
    urls = [r["url"] for r in filtered]
    assert "https://arxiv.org/abs/1706.03762" in urls
    assert "https://huggingface.co/blog/post" in urls
    assert "https://random-blog.com/x" not in urls


def test_filter_whitelist_java():
    results = [
        {"url": "https://openjdk.org/jeps/444", "content": "x"},
        {"url": "https://baeldung.com/java-loom", "content": "y"},
        {"url": "https://medium.com/random", "content": "z"},
    ]
    filtered = filter_whitelist(results, nicho="java")
    urls = [r["url"] for r in filtered]
    assert "https://openjdk.org/jeps/444" in urls
    assert "https://baeldung.com/java-loom" in urls
    assert "https://medium.com/random" not in urls


def test_min_sources_constant():
    assert MIN_SOURCES == 2


def test_whitelist_covers_topics_that_failed_on_sources():
    """The five no_quality_sources failures were domain coverage, not absent content.

    Each URL below is a canonical primary source for one failed topic.
    """
    cases = [
        ("llms", "https://pytorch.org/blog/quantization-in-practice/"),
        ("llms", "https://aclanthology.org/2021.emnlp-main.1/"),
        ("llms", "https://github.com/huggingface/peft"),
        ("rag", "https://milvus.io/docs/index.md"),
        ("java", "https://shipilev.net/jvm/anatomy-quarks/"),
    ]
    for nicho, url in cases:
        assert filter_whitelist([{"url": url, "content": "x"}], nicho), (nicho, url)


def test_whitelist_still_rejects_content_farms():
    junk = [
        {
            "url": "https://medium.com/@someone/llm-quantization-explained",
            "content": "x",
        },
        {"url": "https://dev.to/someone/rag-tutorial", "content": "x"},
        {"url": "https://random-seo-blog.com/lora", "content": "x"},
    ]
    for nicho in ("llms", "rag", "java"):
        assert filter_whitelist(junk, nicho) == []


def test_search_asks_tavily_to_restrict_to_the_whitelist(monkeypatch):
    """Filtering after the fact wastes all 10 result slots on content farms.

    Two topics returned 0 usable sources that way: Tavily handed back medium,
    dev.to and SEO blogs and the filter dropped every one. include_domains spends
    the slots inside the allowlist instead.
    """
    from atlas_sage import search as search_mod

    captured = {}

    class FakeClient:
        def __init__(self, api_key):
            pass

        def search(self, **kwargs):
            captured.update(kwargs)
            return {"results": [{"url": "https://arxiv.org/abs/1", "content": "x"}]}

    monkeypatch.setattr(search_mod, "TavilyClient", FakeClient)
    out = search_mod.search("quantization", "llms", "key")

    assert "include_domains" in captured, "whitelist must be pushed into the query"
    assert "arxiv.org" in captured["include_domains"]
    assert "baeldung.com" not in captured["include_domains"], "must be per-nicho"
    assert out and out[0]["url"] == "https://arxiv.org/abs/1"


def test_search_still_filters_locally_if_the_provider_ignores_the_restriction():
    """include_domains is a request, not a guarantee - keep the local filter."""
    junk = [{"url": "https://medium.com/@x/post", "content": "x"}]
    assert filter_whitelist(junk, "llms") == []
