from __future__ import annotations

from urllib.parse import urlparse

from tavily import TavilyClient

MIN_SOURCES = 2
MAX_SOURCES = 5

_COMMON_ML = {
    "arxiv.org",
    "anthropic.com",
    "openai.com",
    "huggingface.co",
    "simonwillison.net",
    "lilianweng.github.io",
    "ai.googleblog.com",
    "research.google",
    "blog.research.google",
    "deepmind.com",
    "deepmind.google",
    "ai.meta.com",
    "engineering.fb.com",
    "research.microsoft.com",
    "sebastianraschka.com",
    "jalammar.github.io",
    "karpathy.github.io",
    "karpathy.ai",
    "distill.pub",
    "thegradient.pub",
    "d2l.ai",
    "nlp.seas.harvard.edu",
    "machinelearningmastery.com",
    "en.wikipedia.org",
    "ibm.com",
    "nvidia.com",
    "developer.nvidia.com",
    "aws.amazon.com",
    # Added after five topics failed with no_quality_sources: quantization, LoRA,
    # RoPE/context scaling, tokenization and vector index types. The content
    # exists, it just lives on primary sources this list did not cover.
    "pytorch.org",
    "aclanthology.org",
    "openreview.net",
    "nlp.stanford.edu",
    "crfm.stanford.edu",
    "bair.berkeley.edu",
    "eleuther.ai",
    "lightning.ai",
    "blog.vllm.ai",
    "docs.vllm.ai",
    "databricks.com",
    "cohere.com",
    "mistral.ai",
    "wandb.ai",
    # ponytail: github.com is the widest entry here and the only one that can let
    # a low-quality repo through. It stays because the canonical docs for LoRA
    # (huggingface/peft), quantization (llama.cpp) and ANN indexes (faiss) are
    # READMEs, not blog posts. The critic and MIN_SOURCES are the backstop; drop
    # it if junk starts reaching the vault.
    "github.com",
}

WHITELIST = {
    "llms": _COMMON_ML
    | {
        "arize.com",
    },
    "rag": _COMMON_ML
    | {
        "langchain.com",
        "blog.langchain.dev",
        "llamaindex.ai",
        "pinecone.io",
        "weaviate.io",
        "qdrant.tech",
        "jina.ai",
        "elastic.co",
        "vespa.ai",
        "milvus.io",
        "zilliz.com",
        "trychroma.com",
        "redis.io",
    },
    "java": {
        "openjdk.org",
        "oracle.com",
        "docs.oracle.com",
        "inside.java",
        "dev.java",
        "baeldung.com",
        "infoq.com",
        "spring.io",
        "jakarta.ee",
        "jetbrains.com",
        "blog.jetbrains.com",
        "en.wikipedia.org",
        # GC internals live on the maintainers' own sites, not on the vendor docs.
        "shipilev.net",
        "malloc.se",
        "tschatzl.github.io",
        "developers.redhat.com",
        "azul.com",
    },
}


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host.removeprefix("www.")


def filter_whitelist(results: list[dict], nicho: str) -> list[dict]:
    allowed = WHITELIST.get(nicho, set())
    out = []
    for r in results:
        d = _domain(r["url"])
        if any(d == a or d.endswith("." + a) for a in allowed):
            out.append(r)
    return out


def search(topic: str, nicho: str, api_key: str) -> list[dict]:
    # Push the allowlist into the query instead of filtering afterwards. Filtering
    # after the fact spends all ten result slots on whatever ranks highest for the
    # topic, which for quantization and GC internals was entirely content farms
    # (medium, dev.to, dzone, youtube) and left zero usable sources. Asking for
    # results inside the allowlist spends the same ten slots on primary material.
    client = TavilyClient(api_key=api_key)
    response = client.search(
        query=topic,
        max_results=10,
        search_depth="advanced",
        include_domains=sorted(WHITELIST.get(nicho, set())),
    )
    raw = response.get("results", [])
    # Kept as a backstop: include_domains is a request to the provider, not a
    # guarantee, and a stray domain must never reach the vault.
    filtered = filter_whitelist(raw, nicho)
    return filtered[:MAX_SOURCES]
