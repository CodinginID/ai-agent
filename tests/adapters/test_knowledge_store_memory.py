"""Unit tests untuk InMemoryKnowledgeStore.

Validasi behavior port KnowledgeStore lewat in-memory adapter — paling lengkap
karena tidak butuh Postgres + pgvector running. PgVectorKnowledgeStore di-test
terpisah di integration test (pakai real Neon test instance, kalau env tersedia).
"""

from __future__ import annotations

import math

import pytest

from app.adapters.knowledge_store_memory import (
    InMemoryKnowledgeStore,
    _cosine_similarity,
)

# ── _cosine_similarity helper ─────────────────────────────────────────────────


def test_cosine_similarity_identical_vectors_returns_one() -> None:
    assert math.isclose(_cosine_similarity([1, 2, 3], [1, 2, 3]), 1.0)


def test_cosine_similarity_orthogonal_vectors_returns_zero() -> None:
    assert math.isclose(_cosine_similarity([1, 0], [0, 1]), 0.0)


def test_cosine_similarity_opposite_vectors_returns_minus_one() -> None:
    assert math.isclose(_cosine_similarity([1, 0], [-1, 0]), -1.0)


def test_cosine_similarity_zero_vector_returns_zero() -> None:
    assert _cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0


def test_cosine_similarity_empty_returns_zero() -> None:
    assert _cosine_similarity([], [1, 2]) == 0.0


# ── index + fetch round-trip ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_index_returns_id_string() -> None:
    store = InMemoryKnowledgeStore()
    chunk_id = await store.index("proj-1", "hello world", [0.1, 0.2, 0.3])
    assert isinstance(chunk_id, str)
    assert len(chunk_id) > 0


@pytest.mark.asyncio
async def test_recall_returns_indexed_chunk() -> None:
    store = InMemoryKnowledgeStore()
    await store.index("proj-1", "the answer is 42", [1.0, 0.0, 0.0])
    results = await store.recall("proj-1", [1.0, 0.0, 0.0], k=5)
    assert len(results) == 1
    assert results[0].chunk.text == "the answer is 42"
    assert math.isclose(results[0].score, 1.0)


@pytest.mark.asyncio
async def test_recall_meta_preserved() -> None:
    store = InMemoryKnowledgeStore()
    await store.index(
        "proj-1", "x", [1.0, 0.0],
        meta={"role": "engineer", "task_id": "abc"},
    )
    results = await store.recall("proj-1", [1.0, 0.0], k=1)
    assert results[0].chunk.meta == {"role": "engineer", "task_id": "abc"}


# ── Project isolation ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recall_does_not_cross_projects() -> None:
    """Acceptance: dua project punya scratchpad terpisah — RAG juga harus."""
    store = InMemoryKnowledgeStore()
    await store.index("proj-A", "A content", [1.0, 0.0, 0.0])
    await store.index("proj-B", "B content", [1.0, 0.0, 0.0])

    a = await store.recall("proj-A", [1.0, 0.0, 0.0])
    b = await store.recall("proj-B", [1.0, 0.0, 0.0])

    assert len(a) == 1 and a[0].chunk.text == "A content"
    assert len(b) == 1 and b[0].chunk.text == "B content"


@pytest.mark.asyncio
async def test_recall_empty_project_returns_empty_list() -> None:
    store = InMemoryKnowledgeStore()
    await store.index("proj-A", "x", [1.0])
    results = await store.recall("proj-empty", [1.0], k=5)
    assert results == []


# ── Top-K ordering ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recall_orders_by_similarity_descending() -> None:
    store = InMemoryKnowledgeStore()
    await store.index("p", "less similar",  [1.0, 1.0, 0.0])  # cos ~0.71 to [1,0,0]
    await store.index("p", "most similar",  [1.0, 0.0, 0.0])  # cos 1.0
    await store.index("p", "orthogonal",    [0.0, 1.0, 0.0])  # cos 0.0

    results = await store.recall("p", [1.0, 0.0, 0.0], k=3)
    assert [r.chunk.text for r in results] == [
        "most similar", "less similar", "orthogonal"
    ]
    assert results[0].score > results[1].score > results[2].score


@pytest.mark.asyncio
async def test_recall_limits_to_k() -> None:
    store = InMemoryKnowledgeStore()
    for i in range(10):
        await store.index("p", f"chunk-{i}", [float(i), 0.0])
    results = await store.recall("p", [5.0, 0.0], k=3)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_recall_returns_all_if_k_larger_than_corpus() -> None:
    store = InMemoryKnowledgeStore()
    await store.index("p", "only", [1.0])
    results = await store.recall("p", [1.0], k=100)
    assert len(results) == 1


# ── delete_project ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_project_removes_all_chunks_in_that_project() -> None:
    store = InMemoryKnowledgeStore()
    await store.index("doomed", "x", [1.0])
    await store.index("doomed", "y", [0.5])
    await store.index("survives", "z", [1.0])

    n = await store.delete_project("doomed")
    assert n == 2
    assert await store.recall("doomed", [1.0]) == []
    remaining = await store.recall("survives", [1.0])
    assert len(remaining) == 1


@pytest.mark.asyncio
async def test_delete_project_returns_zero_when_nothing_to_delete() -> None:
    store = InMemoryKnowledgeStore()
    await store.index("p", "x", [1.0])
    assert await store.delete_project("ghost") == 0


# ── Port conformance ─────────────────────────────────────────────────────────


def test_in_memory_store_satisfies_knowledge_store_protocol() -> None:
    """Structural typing check — InMemory adapter punya signature yang dibutuhkan port."""
    from app.ports.knowledge_store import KnowledgeStore
    store: KnowledgeStore = InMemoryKnowledgeStore()
    # Pass kalau type-check tidak protes; runtime cuma assert attribute presence.
    assert hasattr(store, "index")
    assert hasattr(store, "recall")
    assert hasattr(store, "delete_project")
