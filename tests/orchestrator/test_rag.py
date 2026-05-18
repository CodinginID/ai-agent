"""Unit tests untuk RAG helpers (``enrich_prompt_with_recall``, ``index_task_result``)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.adapters.knowledge_store_memory import InMemoryKnowledgeStore
from app.orchestrator.rag import (
    MAX_RECALL_CONTEXT_CHARS,
    enrich_prompt_with_recall,
    index_task_result,
)


@dataclass
class FakeEmbedder:
    """Deterministic embedder for tests. Hash each unique text to a fixed vector."""

    dim: int = 3

    @property
    def dimension(self) -> int:
        return self.dim

    def embed(self, text: str) -> list[float]:
        # Deterministic: same text → same vector, different texts → different vectors.
        h = hash(text) % 1000
        return [float(h % 10), float((h // 10) % 10), float((h // 100) % 10)]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class ExplodingEmbedder:
    """Embedder yang selalu raise — untuk test gagal-silently."""

    dimension = 3

    def embed(self, text: str) -> list[float]:
        raise RuntimeError("embedder boom")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedder boom")


# ── enrich_prompt_with_recall ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enrich_no_op_when_embedder_is_none() -> None:
    store = InMemoryKnowledgeStore()
    out = await enrich_prompt_with_recall(
        project_id="p", prompt="halo", embedder=None, store=store, k=5,
    )
    assert out == "halo"


@pytest.mark.asyncio
async def test_enrich_no_op_when_prompt_empty() -> None:
    embedder = FakeEmbedder()
    store = InMemoryKnowledgeStore()
    out = await enrich_prompt_with_recall(
        project_id="p", prompt="   ", embedder=embedder, store=store, k=5,
    )
    assert out == "   "


@pytest.mark.asyncio
async def test_enrich_returns_prompt_when_no_hits() -> None:
    embedder = FakeEmbedder()
    store = InMemoryKnowledgeStore()  # empty
    out = await enrich_prompt_with_recall(
        project_id="p", prompt="tanya X", embedder=embedder, store=store, k=5,
    )
    assert out == "tanya X"


@pytest.mark.asyncio
async def test_enrich_prepends_recall_block() -> None:
    embedder = FakeEmbedder()
    store = InMemoryKnowledgeStore()
    # Embed prompt manually, index something with the same embedding so recall finds it.
    same_embed = embedder.embed("query text")
    await store.index("p", "previous result A", same_embed)

    out = await enrich_prompt_with_recall(
        project_id="p", prompt="query text", embedder=embedder, store=store, k=5,
    )
    assert "Konteks relevant dari project memory:" in out
    assert "previous result A" in out
    assert out.endswith("query text")  # original prompt at the end


@pytest.mark.asyncio
async def test_enrich_respects_project_isolation() -> None:
    embedder = FakeEmbedder()
    store = InMemoryKnowledgeStore()
    same_embed = embedder.embed("shared query")
    await store.index("proj-A", "A-only context", same_embed)
    await store.index("proj-B", "B-only context", same_embed)

    out_a = await enrich_prompt_with_recall(
        project_id="proj-A", prompt="shared query", embedder=embedder, store=store, k=5,
    )
    out_b = await enrich_prompt_with_recall(
        project_id="proj-B", prompt="shared query", embedder=embedder, store=store, k=5,
    )
    assert "A-only context" in out_a and "B-only context" not in out_a
    assert "B-only context" in out_b and "A-only context" not in out_b


@pytest.mark.asyncio
async def test_enrich_truncates_when_context_exceeds_cap() -> None:
    embedder = FakeEmbedder()
    store = InMemoryKnowledgeStore()
    big_chunk = "X" * (MAX_RECALL_CONTEXT_CHARS + 500)
    same_embed = embedder.embed("query")
    await store.index("p", big_chunk, same_embed)

    out = await enrich_prompt_with_recall(
        project_id="p", prompt="query", embedder=embedder, store=store, k=5,
    )
    # Should contain truncation marker
    assert "(truncated)" in out


@pytest.mark.asyncio
async def test_enrich_fails_silently_on_embedder_error() -> None:
    """Embedder explodes → return original prompt, jangan raise."""
    embedder = ExplodingEmbedder()
    store = InMemoryKnowledgeStore()
    out = await enrich_prompt_with_recall(
        project_id="p", prompt="ok", embedder=embedder, store=store, k=5,
    )
    assert out == "ok"


# ── index_task_result ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_index_no_op_when_embedder_none() -> None:
    store = InMemoryKnowledgeStore()
    result = await index_task_result(
        project_id="p", prompt="p", output="o",
        role="engineer", agent="codex",
        embedder=None, store=store,
    )
    assert result is None
    # store should be empty
    assert await store.recall("p", [0.0, 0.0, 0.0]) == []


@pytest.mark.asyncio
async def test_index_no_op_when_output_empty() -> None:
    embedder = FakeEmbedder()
    store = InMemoryKnowledgeStore()
    result = await index_task_result(
        project_id="p", prompt="prompt", output="   ",
        role="engineer", agent="codex",
        embedder=embedder, store=store,
    )
    assert result is None


@pytest.mark.asyncio
async def test_index_stores_chunk_with_meta() -> None:
    embedder = FakeEmbedder()
    store = InMemoryKnowledgeStore()
    chunk_id = await index_task_result(
        project_id="p", prompt="refactor X", output="here is the refactor",
        role="engineer", agent="codex",
        embedder=embedder, store=store,
        extra_meta={"job_id": "job-123"},
    )
    assert chunk_id is not None

    # Retrieve via recall to verify
    same_embed = embedder.embed("here is the refactor")
    hits = await store.recall("p", same_embed, k=1)
    assert len(hits) == 1
    assert hits[0].chunk.text == "here is the refactor"
    meta = hits[0].chunk.meta
    assert meta["role"] == "engineer"
    assert meta["agent"] == "codex"
    assert meta["prompt"] == "refactor X"
    assert meta["job_id"] == "job-123"


@pytest.mark.asyncio
async def test_index_silently_returns_none_on_embedder_failure() -> None:
    embedder = ExplodingEmbedder()
    store = InMemoryKnowledgeStore()
    result = await index_task_result(
        project_id="p", prompt="p", output="o",
        role="engineer", agent="codex",
        embedder=embedder, store=store,
    )
    assert result is None
