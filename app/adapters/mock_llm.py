"""Mock AI provider — deterministik, TANPA API key. Untuk mode dev/testing.

Mendeteksi jenis prompt (intent / planning / loop think / loop reflect / chat /
summarize) lewat marker string, lalu mengembalikan respons valid sehingga
seluruh alur orchestrator bisa dites end-to-end tanpa memanggil LLM cloud.

Aktifkan dengan memilih provider ``mock`` — mis. ``AI_PROVIDER_DEFAULT=mock``
atau preferensi per-user. Mode IT-Manager "asli" baru aktif saat user memasukkan
API key (provider anthropic/glm) via frontend.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

_MOCK_CHAT_REPLY = (
    "[mock] Halo! Mode mock aktif (tanpa LLM asli). Untuk mengaktifkan "
    "IT-Manager sungguhan, masukkan API key provider kamu lewat frontend."
)


class MockAIProvider:
    """Implement ``AIProvider`` port dengan respons kaleng deterministik."""

    def chat(self, prompt: str) -> str:
        p = prompt.lower()

        # 1. Intent parser fallback → JSON intent yang valid.
        if "json intent parser" in p:
            return json.dumps({
                "intent": "chat", "project_id": "default",
                "confidence": 0.9, "requires_approval": False,
                "parameters": {}, "reason": "[mock] intent classification",
            })

        # 2. PM planning → TaskPlan JSON 2 langkah (biar alur decompose terlihat).
        if "project manager ai" in p or "break down this request" in p:
            return json.dumps({
                "title": "[mock] Rencana tugas",
                "summary": "[mock] rencana dua langkah untuk demo alur IT-Manager",
                "estimated_complexity": "simple",
                "steps": [
                    {"order": 1, "description": "Cek status server", "action": "server_status", "params": {}},
                    {"order": 2, "description": "Cek penggunaan disk", "action": "disk_usage", "params": {}},
                ],
            })

        # 3. Loop REFLECT → anggap selesai (hindari retry tak berujung).
        if "did this fully address the request" in p:
            return json.dumps({"satisfied": True, "reason": "[mock] cukup"})

        # 4. Loop THINK → keputusan "respond" (tanpa jalankan command nyata).
        if "respond only with valid json" in p and '"action"' in prompt:
            return json.dumps({
                "action": "respond",
                "text": "[mock] Selesai — respons dummy dari mode mock.",
            })

        # 5. Summarize output aksi.
        if "ringkas output" in p:
            return "[mock] Ringkasan: output diterima (mode mock, tanpa LLM asli)."

        # 6. Chat umum / fallback.
        return _MOCK_CHAT_REPLY

    def chat_stream(self, prompt: str) -> Iterator[str]:
        text = self.chat(prompt)
        for i, word in enumerate(text.split(" ")):
            yield word if i == 0 else " " + word
