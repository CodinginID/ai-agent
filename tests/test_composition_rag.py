"""Tests untuk composition factory RAG — pilih embedder + store sesuai env."""

from __future__ import annotations

import importlib

import pytest

from app.adapters.embedder_fastembed import FastEmbedAdapter
from app.adapters.embedder_ollama import OllamaEmbedder
from app.adapters.knowledge_store_memory import InMemoryKnowledgeStore


@pytest.fixture(autouse=True)
def _clear_lru_cache_and_reload(monkeypatch: pytest.MonkeyPatch):
    """Reset lru_cache di composition + reload settings setiap test."""
    yield
    import app.composition as comp
    import app.config as cfg
    comp._embedder.cache_clear()
    comp._knowledge_store.cache_clear()
    cfg.settings = cfg.load_settings()


def _reload_settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import app.composition as comp
    import app.config as cfg
    comp._embedder.cache_clear()
    comp._knowledge_store.cache_clear()
    importlib.reload(cfg)
    importlib.reload(comp)


# ── _embedder ────────────────────────────────────────────────────────────────


def test_embedder_default_is_fastembed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMBEDDER_BACKEND", raising=False)
    monkeypatch.delenv("RAG_ENABLED", raising=False)
    _reload_settings(monkeypatch)
    from app.composition import _embedder
    e = _embedder()
    assert isinstance(e, FastEmbedAdapter)


def test_embedder_returns_none_when_rag_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _reload_settings(monkeypatch, RAG_ENABLED="false")
    from app.composition import _embedder
    assert _embedder() is None


def test_embedder_returns_none_when_backend_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _reload_settings(monkeypatch, EMBEDDER_BACKEND="none")
    from app.composition import _embedder
    assert _embedder() is None


def test_embedder_ollama_when_backend_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    _reload_settings(monkeypatch, EMBEDDER_BACKEND="ollama")
    from app.composition import _embedder
    e = _embedder()
    assert isinstance(e, OllamaEmbedder)


def test_embedder_raises_on_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    _reload_settings(monkeypatch, EMBEDDER_BACKEND="brain-soup")
    from app.composition import _embedder
    with pytest.raises(ValueError, match="EMBEDDER_BACKEND"):
        _embedder()


# ── _knowledge_store ─────────────────────────────────────────────────────────


def test_knowledge_store_sqlite_default_to_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test/dev SQLite tidak support pgvector — fallback ke in-memory."""
    _reload_settings(monkeypatch, DATABASE_URL="sqlite:///:memory:")
    from app.composition import _knowledge_store
    assert isinstance(_knowledge_store(), InMemoryKnowledgeStore)


def test_knowledge_store_uses_pgvector_when_postgres_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production URL → PgVectorKnowledgeStore (tanpa actually konek DB)."""
    _reload_settings(
        monkeypatch,
        DATABASE_URL="postgresql://x:y@h:5432/d",
    )
    from app.adapters.knowledge_store_pgvector import PgVectorKnowledgeStore
    from app.composition import _knowledge_store
    assert isinstance(_knowledge_store(), PgVectorKnowledgeStore)
