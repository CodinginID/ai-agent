"""RAG enrichment helpers — pre-dispatch recall + post-job-done indexing.

Extracted from ``worker_ws`` supaya logic-nya testable tanpa WS plumbing.
Bekerja terhadap port abstraction (``Embedder``, ``KnowledgeStore``) —
adapter mana yang dipakai ditentukan di ``composition.py``.

No-op kalau ``embedder is None`` (RAG disabled) — caller boleh memanggil
tanpa cek, asal pass ``None`` saat RAG off.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.ports.embedder import Embedder
    from app.ports.knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)

# Cap input text yang di-embed supaya tidak crash embedder pada hasil agent
# yang super panjang. Cocok dengan ~1k token budget di model lightweight.
MAX_EMBED_CHARS = 4000

# Cap context block yang di-prepend ke prompt supaya tidak meledakkan token
# budget agent target.
MAX_RECALL_CONTEXT_CHARS = 2000


async def enrich_prompt_with_recall(
    *,
    project_id: str,
    prompt: str,
    embedder: Embedder | None,
    store: KnowledgeStore,
    k: int = 5,
) -> str:
    """Kalau ada chunk relevant di project knowledge, prepend ke prompt.

    Gagal silently — kalau embedder error atau recall error, return prompt
    apa adanya. RAG adalah enhancement, bukan critical path.
    """
    if embedder is None or not prompt.strip():
        return prompt
    try:
        q_emb = await asyncio.to_thread(embedder.embed, prompt[:MAX_EMBED_CHARS])
        hits = await store.recall(project_id, q_emb, k=k)
    except Exception as exc:
        logger.warning("RAG recall failed: %s", exc)
        return prompt
    if not hits:
        return prompt

    lines = ["Konteks relevant dari project memory:"]
    total = 0
    for i, hit in enumerate(hits, 1):
        text = hit.chunk.text
        if total + len(text) > MAX_RECALL_CONTEXT_CHARS:
            text = text[: MAX_RECALL_CONTEXT_CHARS - total]
            lines.append(f"[{i}] (truncated) {text}…")
            break
        lines.append(f"[{i}] {text}")
        total += len(text)
    return "\n".join(lines) + "\n\n---\n\n" + prompt


async def index_task_result(
    *,
    project_id: str,
    prompt: str,
    output: str,
    role: str,
    agent: str,
    embedder: Embedder | None,
    store: KnowledgeStore,
    extra_meta: dict[str, Any] | None = None,
) -> str | None:
    """Embed output + index ke project memory untuk recall di task berikutnya.

    Return chunk id kalau berhasil, None kalau RAG off atau gagal.
    """
    if embedder is None or not output.strip():
        return None
    text = output[:MAX_EMBED_CHARS]
    try:
        emb = await asyncio.to_thread(embedder.embed, text)
    except Exception as exc:
        logger.warning("RAG embed for index failed: %s", exc)
        return None

    meta: dict[str, Any] = {"role": role, "agent": agent, "prompt": prompt[:500]}
    if extra_meta:
        meta.update(extra_meta)

    try:
        return await store.index(project_id, output, emb, meta=meta)
    except Exception as exc:
        logger.warning("RAG index failed: %s", exc)
        return None
