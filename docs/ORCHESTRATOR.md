# Octopus Orchestrator — Design Blueprint

> Status: **design doc** (belum implementasi). Ditulis setelah audit kode nyata
> pada commit di `main`. Tujuan: menjadikan orchestrator Octopus **secara
> struktural lebih unggul** dari agent monolitik (Hermes/OpenClaw-style) lewat
> tiga pilar: **otak murah-lokal yang berpikir**, **worker mahal-terdistribusi
> yang bekerja (tiap worker bisa LLM berbeda)**, dan **task durable berbasis
> GitHub Issue**.

---

## 1. Audit: apa yang SUDAH ada (bukan tebakan)

Komponen ini sudah ada & ter-wire di repo — fondasinya jauh lebih matang dari
kesan "bot kontrol server":

| Kapabilitas | File | Status |
|---|---|---|
| Intent parsing / routing | `app/intents/parser.py` | ✅ matang |
| Execution loop (observe→think→decide→execute→reflect→retry) | `app/executor/loop.py` (384 baris) | ✅ nyata, ter-wire di `use_cases.py:243` |
| PM Agent (request → `TaskPlan` berisi steps) | `app/agents/pm.py` | 🟡 ada, output belum dieksekusi |
| Worker dispatch ke mesin user (WS) | `app/interfaces/worker_ws.py` `dispatch_agent_job()` | ✅ matang (RAG, hand-off, job persistence) |
| Multi-model worker runner (codex/claude/glm/echo) | `app/tui/_worker.py` `_AGENTS` | ✅ jalan, model via `.env` |
| Worker presence + **capability sets** | `app/adapters/worker_registry.py` `k_caps(user,agent)` | ✅ ada (codex/claude/glm) |
| Job state persistence (survive restart, cross-instance) | `app/adapters/job_store.py` (Redis hash) | ✅ ada |
| RAG recall + index per task | `app/orchestrator/rag.py` | ✅ ada (pgvector) |
| Hand-off context antar-role | `app/adapters/agent_context.py` | ✅ ada |
| GitHub Issues adapter (create/comment/close/list/label) | `app/adapters/github.py` | ✅ ada, lifecycle belum tersambung |
| TUI command center | `app/tui/` (12 file, Textual) | ✅ matang |

## 2. Gap: kenapa orchestrator belum "lebih baik"

Komponennya ada, tapi sebagai **pulau terpisah**. Empat gap inti:

### GAP-1 — Dua sistem eksekusi belum disatukan *(paling kritikal)*
- `ExecutionLoop` (`executor/loop.py`) pintar (reflect/retry) tapi **single-agent**:
  hanya bisa `terminal` / `file_read` / `respond` / `multi_step` **di server lokal**.
  Ia **tidak bisa** mendelegasikan ke worker.
- `dispatch_agent_job` (`worker_ws.py`) kuat (kirim ke Claude/Codex/GLM di mesin
  user, RAG, hand-off) tapi **tanpa loop reflektif** — sekali kirim, sekali terima.

> **Akibat:** loop pintar tak bisa pakai worker kuat; worker kuat tak punya otak
> reflektif. Ini jantung masalahnya.

### GAP-2 — Tidak ada task queue durable
Antar-langkah pakai `asyncio.Queue` in-process. `job_store` menyimpan *state* (Redis
hash, TTL 1 jam) tapi bukan *work queue*. Tidak ada antrian yang bisa di-*resume*
setelah restart, di-*retry* terjadwal, atau dikonsumsi banyak konsumen.

### GAP-3 — Rantai PM → Issue → Worker → Close terputus
`PMAgent.plan()` menghasilkan `TaskPlan` tapi tidak ada yang mengeksekusi step-nya,
membuat GitHub Issue sebagai catatan task, lalu menutupnya saat selesai. Semua
bahannya ada; rantainya belum dirangkai.

### GAP-4 — Pemilihan worker & model belum cerdas
- Worker dipilih `random.choice` (`worker_ws.py:349`) — belum role/capability-aware.
- Model worker fixed via `.env` global (`claude_model`, `codex_model`, `glm_model`)
  — belum **per-worker / per-task / per-role**.

---

## 3. Arsitektur target

```
 Telegram / TUI
      │  natuial language request
      ▼
┌─────────────────────────────────────────────────────────────┐
│ QWEN ORCHESTRATOR  (lokal, gratis, privat)                    │
│  1. classify complexity        (intents/parser.py — ADA)      │
│  2. decompose → TaskPlan        (agents/pm.py — ADA)          │
│  3. for each step: pick ROLE + MODEL  (router — BARU, GAP-4)  │
│  4. reflect on results, decide retry  (executor/loop.py — ADA)│
└───────────────┬───────────────────────────────────────────────┘
                │ creates / updates
        ┌───────▼────────────────────────────┐
        │ GITHUB ISSUE = durable task record  │  (adapters/github.py — ADA,
        │  PRD, steps as checklist, attempt    │   lifecycle BARU, GAP-3)
        │  logs as comments, close on done     │
        └───────┬─────────────────────────────┘
                │ enqueue step (DURABLE)
        ┌───────▼────────────────────────────┐
        │ TASK QUEUE  (Redis Streams)         │  (BARU, GAP-2; reuse Redis)
        │  survive restart, consumer groups   │
        └───────┬─────────────────────────────┘
                │ dispatch by (role, capability)
        ┌───────▼─────────────────────────────────────────────┐
        │ WORKER POOL  (mesin user, via worker_ws — ADA)        │
        │  capability-aware pick (worker_registry.k_caps — ADA) │
        │                                                       │
        │  ENGINEER  → claude   (deep coding)                   │
        │  REVIEWER  → glm/gemini (cross-check, cheaper)        │
        │  INFRA     → qwen lokal (server ops, privat)          │
        │  RESEARCH  → codex    (exploration)                   │
        │     ▲ tiap worker LLM BERBEDA — pilar utama           │
        └───────┬─────────────────────────────────────────────┘
                │ stream results + hand-off context (agent_context — ADA)
        ┌───────▼─────────────────────────────┐
        │ REFLECTION  (Qwen, di server, murah) │  (executor/loop.py — ADA,
        │  satisfied? → close issue            │   extend untuk delegate)
        │  failed?    → retry w/ new context   │
        └──────────────────────────────────────┘
```

## 4. Pilar pembeda — "tiap worker LLM berbeda"

Ini keunggulan struktural Octopus atas agent monolitik. Tiga lapis keputusan:

### 4a. Role → Model mapping (rule-based dulu, bukan LLM)
Tabel deklaratif di config — murah, deterministik, mudah di-tes:

| Role | Default model/agent | Alasan |
|---|---|---|
| `engineer` | `claude` | reasoning coding terbaik |
| `reviewer` | `glm` | cross-check oleh model berbeda → kurangi blind spot |
| `infra` | `qwen` (lokal) | ops server, **tidak boleh** keluar mesin (privasi) |
| `research` | `codex` | eksplorasi, baca kode |
| `planner` | `qwen` (lokal) | dekomposisi murah & sering |

> **Kenapa lebih baik dari Hermes:** satu model untuk semua = boros + blind spot
> seragam. Octopus pakai **model termurah yang cukup** per peran, dan **reviewer
> sengaja beda model** dari engineer supaya menangkap kesalahan yang model sama
> akan lewatkan.

### 4b. Capability-aware worker pick
Ganti `random.choice` dengan: cek `k_caps(user_id, agent)` di `worker_registry` →
hanya pilih worker yang **punya CLI model itu terpasang**. Worker kirim daftar
kapabilitas saat connect (sebagian sudah: registry punya slot caps).

### 4c. Per-task model override
`TaskStep` & `dispatch_agent_job(extra=...)` membawa `model` opsional, sehingga
orchestrator (atau user) bisa override default role→model untuk task tertentu.
`_AGENTS` runner dimodifikasi menerima `model` dari payload, bukan hanya `.env`.

---

## 5. Roadmap implementasi (urutan prioritas + bisa di-PR terpisah)

Tiap item = satu PR (sesuai aturan repo: satu concern, conventional commit, CI hijau).

### PR-1 — Satukan loop + worker *(fondasi, GAP-1)*
- Tambah aksi `delegate` ke `LLMDecision` di `executor/loop.py`:
  `{"action":"delegate","role":"engineer","prompt":"..."}`
- `ExecutionLoop` memanggil dispatcher worker untuk aksi `delegate`, hasilnya masuk
  ke fase **reflect** yang sudah ada. Loop tetap di server (Qwen), kerja berat di worker.
- Port baru `WorkerDispatchPort` (Protocol) supaya domain tetap bersih (hexagonal).
- Test: loop yang memutuskan delegate → mock dispatcher → reflect → finalize.

### PR-2 — Role→Model router *(GAP-4, pilar utama)*
- `app/orchestrator/router.py`: fungsi murni `pick(role, available_caps) -> (agent, model)`.
- Tabel role→model di `config.py` (env-overridable).
- `dispatch_agent_job` & `_AGENTS` runner terima `model` dari payload.
- Capability-aware pick di `worker_ws._pick_worker` (pakai `k_caps`).
- Test: matriks role × caps → agent/model benar; fallback saat cap absen.

### PR-3 — Task queue durable *(GAP-2)* ✅ DONE (#TBD)
- Adapter `app/adapters/task_queue.py` pakai **Redis Streams** (`XADD`/`XREADGROUP`
  + consumer group `dispatchers`). Tidak perlu Celery/RQ — Redis sudah ada di stack.
- Step di-*enqueue*, konsumer = dispatcher; `ack` saat selesai, `reclaim`
  (`XAUTOCLAIM`, idle > threshold) re-deliver pending yang nyangkut saat crash.
- Port `app/ports/task_queue.py` (`TaskQueuePort`, `QueuedStep`) — hexagonal.
- Test: enqueue → consume → ack; pending re-claim setelah "crash" (10 test).

### PR-4 — Rantai PM → Issue → Worker → Close *(GAP-3)*
- `app/orchestrator/task_runner.py`: `TaskPlan` → buat GitHub Issue (PRD + steps
  checklist) → enqueue tiap step → dispatch by role → comment log per attempt →
  reflect → `close_issue` saat semua step satisfied.
- Test: plan 2-step → mock github + mock dispatcher → issue dibuat, dikomentari, ditutup.

### Wiring end-to-end ✅ DONE (#TBD)
- `composition.build_task_runner()` — rakit `PMAgent` + `GitHubAdapter` + `WorkerDispatchAdapter`.
- Endpoint Core `POST /tasks/run` (`app/interfaces/tasks.py`) — auth admin/session
  sama seperti `/chat/send`; 503 eksplisit kalau GITHUB_TOKEN/REPO kosong.
- Command Telegram `/task <deskripsi>` (`telegram-adapter/main.py`) → panggil
  `/tasks/run`, tampilkan link issue + status tiap step + apakah ditutup.
- Test: 7 endpoint test (closed/failed/no-step/503/admin-needs-email).

### PR-5 — Observability *(opsional, mempertajam)*
- Structured log `[TIME][ROLE][TASK_ID][STATUS]` + korelasi `job_id`/`issue`.
- Endpoint `/tasks` untuk TUI task board (data sudah di job_store + issue).

---

## 6. Prinsip yang dijaga (jangan langgar saat implementasi)

- **Hexagonal tetap suci**: domain tak impor adapter. Delegasi worker masuk lewat
  **port** (`WorkerDispatchPort`), bukan import langsung di `use_cases.py`.
- **Qwen lokal = otak default**: semua keputusan rutin (routing, reflect, decompose)
  di Qwen. Model cloud hanya untuk *kerja berat aktual* di worker. Ini menjaga
  ekonomi + privasi — pembeda inti dari agent monolitik cloud.
- **Privasi per-role**: role `infra` (ops server) **wajib** model lokal — jangan
  pernah route ke cloud.
- **Durable > ephemeral**: state penting (task, attempt, hasil) ke Redis/Issue,
  bukan memori proses. Harus survive restart & multi-instance (swarm).
- **Satu PR = satu concern**, semua dengan test (aturan AGENTS.md/CLAUDE.md).

---

## 7. Kenapa hasil akhirnya mengalahkan agent monolitik

| Dimensi | Agent monolitik (Hermes/OpenClaw) | Octopus (target) |
|---|---|---|
| Otak | satu model mahal untuk semua | Qwen lokal untuk berpikir, cloud hanya untuk kerja |
| Worker | satu lingkungan, satu model | terdistribusi, **tiap worker LLM berbeda per role** |
| Review | model sama (blind spot seragam) | reviewer **sengaja beda model** → tangkap error lebih banyak |
| Task | ephemeral (hilang saat restart) | **GitHub Issue durable** + Redis Streams, resume-able |
| Privasi | konteks ke cloud | ops/infra tetap lokal; data sensitif tak keluar mesin |
| Biaya | tinggi (mikir = token mahal) | rendah (mikir = Qwen gratis) |
| Audit | log internal | Issue + comment = jejak kolaboratif yang bisa ditinjau manusia |

Intinya: **bukan model yang membuat sistem pintar — melainkan loop, orkestrasi,
refleksi, dan observasi lingkungan.** Octopus mengejar itu dengan ekonomi &
privasi yang tidak dimiliki agent monolitik cloud.
