"""Unit tests for RagTaskMemory — task-level planning recall + index (RAG).

Embedder and KnowledgeStore are fakes; the DB project resolver is monkeypatched.
We verify: recall filters to task_plan chunks and prepends them, an unset
embedder / backend error degrades gracefully, and index tags chunks correctly.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.adapters import task_memory as tm
from app.adapters.task_memory import RagTaskMemory
from app.ports.knowledge_store import KnowledgeChunk, RecallResult


class FakeEmbedder:
    @property
    def dimension(self) -> int:
        return 3

    def embed(self, text: str) -> list[float]:
        return [float(len(text)), 1.0, 0.0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class FakeStore:
    def __init__(self, hits: list[RecallResult] | None = None) -> None:
        self._hits = hits or []
        self.indexed: list[tuple[str, str, dict[str, Any]]] = []

    async def index(self, project_id, text, embedding, meta=None):  # type: ignore[no-untyped-def]
        self.indexed.append((project_id, text, dict(meta or {})))
        return "chunk-1"

    async def recall(self, project_id, query_embedding, k=5):  # type: ignore[no-untyped-def]
        return self._hits

    async def delete_project(self, project_id):  # type: ignore[no-untyped-def]
        return 0


class BrokenStore(FakeStore):
    async def recall(self, project_id, query_embedding, k=5):  # type: ignore[no-untyped-def]
        raise RuntimeError("pgvector down")


def _chunk(text: str, kind: str) -> RecallResult:
    return RecallResult(
        chunk=KnowledgeChunk(id="c", project_id="p1", text=text, meta={"kind": kind}),
        score=0.9,
    )


@pytest.fixture(autouse=True)
def _patch_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tm, "_resolve_project_id", lambda _u: "p1")


@pytest.mark.asyncio
async def test_recall_disabled_when_embedder_none() -> None:
    mem = RagTaskMemory(embedder=None, store=FakeStore())
    out = await mem.recall_for_planning("u1", "build X", "base ctx")
    assert out == "base ctx"


@pytest.mark.asyncio
async def test_recall_prepends_only_task_plan_chunks() -> None:
    store = FakeStore(hits=[
        _chunk("past task: add auth", "task_plan"),
        _chunk("step output noise", "step_output"),
        _chunk("past task: add cache", "task_plan"),
    ])
    mem = RagTaskMemory(embedder=FakeEmbedder(), store=store, recall_k=3)

    out = await mem.recall_for_planning("u1", "add login", "ORIGINAL")

    assert "add auth" in out
    assert "add cache" in out
    assert "step output noise" not in out   # filtered: wrong kind
    assert out.strip().endswith("ORIGINAL")  # base context preserved at the end


@pytest.mark.asyncio
async def test_recall_no_task_hits_returns_base() -> None:
    store = FakeStore(hits=[_chunk("only step output", "step_output")])
    mem = RagTaskMemory(embedder=FakeEmbedder(), store=store)
    out = await mem.recall_for_planning("u1", "x", "BASE")
    assert out == "BASE"


@pytest.mark.asyncio
async def test_recall_swallows_backend_error() -> None:
    mem = RagTaskMemory(embedder=FakeEmbedder(), store=BrokenStore())
    out = await mem.recall_for_planning("u1", "x", "BASE")
    assert out == "BASE"


@pytest.mark.asyncio
async def test_recall_respects_k_limit() -> None:
    hits = [_chunk(f"task {i}", "task_plan") for i in range(10)]
    store = FakeStore(hits=hits)
    mem = RagTaskMemory(embedder=FakeEmbedder(), store=store, recall_k=2)
    out = await mem.recall_for_planning("u1", "x", "")
    # Only k=2 task chunks rendered (lines [1] and [2], no [3]).
    assert "[1]" in out and "[2]" in out
    assert "[3]" not in out


@pytest.mark.asyncio
async def test_index_tags_chunk_as_task_plan() -> None:
    store = FakeStore()
    mem = RagTaskMemory(embedder=FakeEmbedder(), store=store)

    await mem.index_task("u1", "add login", "implement OAuth", "completed 3 steps")

    assert len(store.indexed) == 1
    _project, text, meta = store.indexed[0]
    assert meta["kind"] == "task_plan"
    assert meta["request"] == "add login"
    assert "implement OAuth" in text


@pytest.mark.asyncio
async def test_index_noop_when_embedder_none() -> None:
    store = FakeStore()
    mem = RagTaskMemory(embedder=None, store=store)
    await mem.index_task("u1", "x", "y", "z")
    assert store.indexed == []
