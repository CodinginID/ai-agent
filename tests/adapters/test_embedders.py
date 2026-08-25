"""Unit tests untuk FastEmbed embedder adapter (dimock supaya tak butuh download)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from app.adapters.embedder_fastembed import FastEmbedAdapter


def _fake_textembedding_class(vectors: list[list[float]]) -> Any:
    """Build a mock that mimics ``fastembed.TextEmbedding`` instance."""
    instance = MagicMock()
    instance.embed.side_effect = lambda texts: iter(vectors[: len(texts)])
    return MagicMock(return_value=instance)


def test_fastembed_dimension_returns_configured() -> None:
    e = FastEmbedAdapter(dim=384)
    assert e.dimension == 384


def test_fastembed_embed_returns_list_of_floats() -> None:
    fake_cls = _fake_textembedding_class([[1.0, 2.0, 3.0]])
    with patch("fastembed.TextEmbedding", fake_cls):
        e = FastEmbedAdapter()
        result = e.embed("hello")
    assert result == [1.0, 2.0, 3.0]
    assert all(isinstance(x, float) for x in result)


def test_fastembed_batch_embed_returns_list_of_vectors() -> None:
    fake_cls = _fake_textembedding_class([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])
    with patch("fastembed.TextEmbedding", fake_cls):
        e = FastEmbedAdapter()
        result = e.embed_batch(["a", "b", "c"])
    assert result == [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]


def test_fastembed_empty_batch_returns_empty_list() -> None:
    """Tidak perlu load model untuk batch kosong."""
    e = FastEmbedAdapter()
    assert e.embed_batch([]) == []


def test_fastembed_lazy_init_only_loads_model_once() -> None:
    fake_cls = _fake_textembedding_class([[1.0], [2.0], [3.0]])
    with patch("fastembed.TextEmbedding", fake_cls):
        e = FastEmbedAdapter()
        e.embed("a")
        e.embed("b")
        e.embed("c")
        assert fake_cls.call_count == 1  # model di-construct sekali


def test_fastembed_satisfies_embedder_protocol() -> None:
    from app.ports.embedder import Embedder
    e: Embedder = FastEmbedAdapter()
    assert hasattr(e, "dimension")
    assert hasattr(e, "embed")
    assert hasattr(e, "embed_batch")
