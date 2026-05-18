"""Unit tests untuk Embedder adapters — fastembed dan Ollama keduanya
dimock supaya test tidak butuh download model atau network call."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.adapters.embedder_fastembed import FastEmbedAdapter
from app.adapters.embedder_ollama import OllamaEmbedder, _l2_normalize
from app.domain.exceptions import AIProviderError

# ── _l2_normalize helper ──────────────────────────────────────────────────────


def test_l2_normalize_unit_vector_unchanged() -> None:
    """Vector dengan norm=1 harus return identik (modulo floating)."""
    import math
    v = [0.6, 0.8]  # norm = 1
    out = _l2_normalize(v)
    assert math.isclose(out[0], 0.6)
    assert math.isclose(out[1], 0.8)


def test_l2_normalize_scales_to_unit_norm() -> None:
    import math
    v = [3.0, 4.0]  # norm = 5
    out = _l2_normalize(v)
    norm = math.sqrt(sum(x * x for x in out))
    assert math.isclose(norm, 1.0)


def test_l2_normalize_zero_vector_returns_zero() -> None:
    assert _l2_normalize([0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]


# ── FastEmbedAdapter (dengan mock) ────────────────────────────────────────────


def _fake_textembedding_class(vectors: list[list[float]]) -> Any:
    """Build a mock that mimics ``fastembed.TextEmbedding`` instance."""
    instance = MagicMock()
    # FastEmbed.embed() yields generator of numpy-array-likes.
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
    e = FastEmbedAdapter()  # tidak akan instantiate TextEmbedding
    assert e.embed_batch([]) == []


def test_fastembed_lazy_init_only_loads_model_once() -> None:
    fake_cls = _fake_textembedding_class([[1.0], [2.0], [3.0]])
    with patch("fastembed.TextEmbedding", fake_cls):
        e = FastEmbedAdapter()
        e.embed("a")
        e.embed("b")
        e.embed("c")
        assert fake_cls.call_count == 1  # model di-construct sekali


# ── OllamaEmbedder (dengan mock requests) ─────────────────────────────────────


def _post_resp(payload: dict[str, Any], status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(response=r)
    return r


def test_ollama_embedder_dimension_returns_configured() -> None:
    e = OllamaEmbedder(url="http://x", dim=768)
    assert e.dimension == 768


def test_ollama_embed_returns_normalized_vector() -> None:
    """Ollama biasa return non-normalized; adapter harus normalize."""
    import math
    with patch("requests.post", return_value=_post_resp({"embedding": [3.0, 4.0]})):
        e = OllamaEmbedder(url="http://localhost:11434")
        out = e.embed("hello")
    norm = math.sqrt(sum(x * x for x in out))
    assert math.isclose(norm, 1.0)


def test_ollama_embed_raises_on_http_error() -> None:
    with patch("requests.post", return_value=_post_resp({"error": "fail"}, status=500)):
        e = OllamaEmbedder(url="http://localhost:11434")
        with pytest.raises(AIProviderError):
            e.embed("hello")


def test_ollama_embed_raises_on_request_exception() -> None:
    with patch("requests.post", side_effect=requests.ConnectionError("down")):
        e = OllamaEmbedder(url="http://localhost:11434")
        with pytest.raises(AIProviderError) as exc:
            e.embed("hello")
    assert "Ollama embed failed" in str(exc.value)


def test_ollama_embed_raises_when_response_missing_embedding() -> None:
    with patch("requests.post", return_value=_post_resp({"foo": "bar"})):
        e = OllamaEmbedder(url="http://localhost:11434")
        with pytest.raises(AIProviderError) as exc:
            e.embed("hello")
    assert "no vector" in str(exc.value)


def test_ollama_embed_batch_calls_embed_per_item() -> None:
    with patch("requests.post", return_value=_post_resp({"embedding": [1.0, 0.0]})):
        e = OllamaEmbedder(url="http://x")
        results = e.embed_batch(["a", "b", "c"])
    assert len(results) == 3


# ── Port conformance ──────────────────────────────────────────────────────────


def test_fastembed_satisfies_embedder_protocol() -> None:
    from app.ports.embedder import Embedder
    e: Embedder = FastEmbedAdapter()
    assert hasattr(e, "dimension")
    assert hasattr(e, "embed")
    assert hasattr(e, "embed_batch")


def test_ollama_satisfies_embedder_protocol() -> None:
    from app.ports.embedder import Embedder
    e: Embedder = OllamaEmbedder(url="http://x")
    assert hasattr(e, "dimension")
    assert hasattr(e, "embed")
    assert hasattr(e, "embed_batch")
