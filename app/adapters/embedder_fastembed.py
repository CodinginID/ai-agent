"""FastEmbed adapter — local CPU embedder.

Default model ``sentence-transformers/all-MiniLM-L6-v2`` (384-dim, ~90 MB).
Model download otomatis ke ``~/.cache/fastembed`` saat instance pertama
dibuat (lazy via ``_get_model``).

FastEmbed sudah L2-normalize output by default, jadi cocok langsung dengan
``KnowledgeStore`` cosine-similarity flow tanpa post-processing.
"""

from __future__ import annotations

from typing import Any

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DIMENSION = 384


class FastEmbedAdapter:
    """Lazy-init: model di-load saat ``embed``/``embed_batch`` dipanggil
    pertama kali. Hindari import-time download saat test discovery.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL, dim: int = DEFAULT_DIMENSION) -> None:
        self._model_name = model_name
        self._dim = dim
        self._model: Any | None = None

    @property
    def dimension(self) -> int:
        return self._dim

    def _get_model(self) -> Any:
        if self._model is None:
            # Import lazy supaya fastembed (yang berat) tidak loaded saat import-time.
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def embed(self, text: str) -> list[float]:
        model = self._get_model()
        # FastEmbed yields generator — ambil first element.
        vector = next(iter(model.embed([text])))
        return [float(x) for x in vector]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        return [[float(x) for x in vec] for vec in model.embed(texts)]
