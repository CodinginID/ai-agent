# Task Planning - Base Features AI Command Center

## 1. Ringkasan

Dokumen ini menerjemahkan PRD `AI Command Center (Multi-Agent VPS Orchestrator)` menjadi rencana implementasi fitur dasar. Fokus awal adalah membangun fondasi aplikasi yang bisa dipakai dari Telegram dan CLI untuk mengontrol VPS, membaca intent user, menjalankan aksi yang tervalidasi, menyimpan konteks project, dan memberi respons ringkas.

Status repo saat ini sudah memiliki fondasi Telegram bot Python dengan:

- Natural language command sederhana berbasis rule + Qwen/Ollama.
- Aksi monitoring server, memory, disk, process, Docker, Git, list file, dan `whoami`.
- Manual command terbatas via `/cmd`.
- Konfigurasi `.env`, Docker Compose, Makefile, dan dokumentasi deployment awal.

Target base features adalah merapikan fondasi tersebut menjadi arsitektur modular yang siap dikembangkan menjadi orchestrator multi-agent.

## 2. Tujuan Base Features

- Menyediakan interface utama melalui Telegram dan interface alternatif melalui CLI.
- Mengubah input user menjadi structured intent yang konsisten.
- Membuat execution plan sederhana sebelum command dijalankan.
- Menjalankan aksi VPS hanya melalui tool/action yang aman dan terdaftar.
- Menyimpan konteks project, riwayat task, keputusan, dan hasil eksekusi.
- Menyiapkan struktur agent PM, Engineer, dan Reviewer meski pada fase awal masih berupa service/prompt terpisah.
- Menyediakan logging audit untuk setiap request, plan, approval, execution, dan response.

## 3. Prinsip Implementasi

- Modular: Telegram, CLI, intent parser, orchestrator, executor, memory, dan safety dipisah.
- Safety-first: semua eksekusi lewat action registry dan whitelist command.
- Observable: setiap aksi punya log terstruktur dan trace ID.
- Incremental: fitur besar dipecah menjadi milestone kecil yang bisa dites.
- Local-first: Qwen/Ollama tetap menjadi default AI runtime sesuai repo saat ini.
- Multi-project-ready: semua state dan command selalu punya konteks project aktif.

## 4. Milestone Implementasi

### Milestone 0 - Baseline & Refactor Fondasi

Tujuan: merapikan `app/bot.py` monolith menjadi modul yang lebih mudah dikembangkan.

Task:

- Buat struktur modul awal:
  - `app/config.py` untuk env/config.
  - `app/interfaces/telegram.py` untuk Telegram handler.
  - `app/interfaces/cli.py` untuk CLI entrypoint.
  - `app/ai/qwen_client.py` untuk komunikasi Ollama/Qwen.
  - `app/intents/parser.py` untuk local + AI intent parser.
  - `app/executor/actions.py` untuk action registry.
  - `app/executor/runner.py` untuk process runner.
  - `app/safety/policy.py` untuk whitelist dan validasi.
  - `app/memory/store.py` untuk penyimpanan context.
  - `app/orchestrator/service.py` untuk alur utama request.
- Pindahkan konfigurasi global dari `bot.py` ke config object.
- Tambahkan test dasar untuk parser lokal, command whitelist, dan format output.
- Pastikan command lama tetap berjalan: `/start`, `/help`, `/whoami`, `/cmd`, `/ask`, `/reset`.

Acceptance criteria:

- Bot berjalan dengan perilaku lama setelah refactor.
- Tidak ada token default hardcoded di source code.
- Unit test untuk parser dan safety policy lulus.
- Modul baru bisa di-import tanpa side effect menjalankan bot.

### Milestone 1 - Project Context & Multi-Project Support

Tujuan: mendukung `/project app1`, `/project app2`, dan menyimpan context per project.

Task:

- Tambahkan model data project:
  - `id`
  - `name`
  - `root_path`
  - `description`
  - `created_at`
  - `updated_at`
  - `active_chat_ids`
- Implementasikan storage awal berbasis JSON di `data/projects.json`.
- Tambahkan command Telegram:
  - `/project` untuk melihat project aktif.
  - `/project <name>` untuk switch project.
  - `/projects` untuk list project.
  - `/project_add <name> <path>` untuk mendaftarkan project.
  - `/project_info` untuk ringkasan context project aktif.
- Pastikan executor menggunakan `root_path` project aktif sebagai working directory.
- Simpan chat history dan execution history per project, bukan global per user saja.

Acceptance criteria:

- User bisa mendaftarkan dan berpindah project dari Telegram.
- `git status`, `ls`, dan command executor berjalan di project aktif.
- Context project tersimpan setelah bot restart.
- Jika project belum dipilih, bot memakai `PROJECT_DIR` sebagai default.

### Milestone 2 - Intent JSON Schema & Plan Generator

Tujuan: semua natural language input diubah menjadi JSON intent dan plan yang eksplisit.

Task:

- Definisikan schema intent:

```json
{
  "intent": "server_status",
  "project_id": "default",
  "confidence": 0.94,
  "requires_approval": false,
  "parameters": {},
  "reason": "User asks to check VPS status"
}
```

- Definisikan schema execution plan:

```json
{
  "plan_id": "uuid",
  "summary": "Check server health",
  "steps": [
    {
      "step_id": "1",
      "action": "server_status",
      "parameters": {},
      "risk": "low"
    }
  ],
  "requires_approval": false
}
```

- Buat prompt Qwen khusus untuk strict JSON intent parsing.
- Tambahkan JSON validation sebelum intent diproses.
- Tambahkan local fallback untuk intent umum agar bot tetap cepat.
- Buat plan generator sederhana yang memetakan intent ke satu atau lebih action.
- Tambahkan response jika AI mengembalikan JSON invalid.

Acceptance criteria:

- Setiap request non-chat menghasilkan intent object yang valid.
- Plan tidak dieksekusi jika schema invalid.
- Intent parser bisa membedakan `chat`, `status`, `docker`, `git`, `deploy`, dan `run_command`.
- Plan generator menghasilkan step yang bisa diaudit sebelum dieksekusi.

### Milestone 3 - Safe Execution Engine

Tujuan: semua eksekusi shell, Docker, dan Git berjalan lewat policy yang aman.

Task:

- Buat action registry berbasis metadata:
  - `name`
  - `description`
  - `risk_level`
  - `allowed_roles`
  - `requires_approval`
  - `handler`
- Pisahkan action low-risk:
  - `server_status`
  - `memory`
  - `disk`
  - `processes`
  - `docker_ps`
  - `docker_images`
  - `docker_stats`
  - `git_status`
  - `list_files`
  - `whoami`
- Tambahkan action medium/high-risk:
  - `docker_restart`
  - `docker_logs`
  - `git_pull`
  - `deploy_restart`
  - `run_command`
- Buat command policy:
  - deny destructive pattern seperti `rm -rf`, `mkfs`, `dd`, fork bomb, redirection ke system path.
  - allow command berdasarkan executable + subcommand.
  - timeout wajib untuk semua subprocess.
  - output dibatasi agar aman untuk Telegram.
- Tambahkan approval flow:
  - Bot mengirim ringkasan plan.
  - User konfirmasi `/approve <plan_id>` atau batalkan `/reject <plan_id>`.
  - Plan pending punya expiry time.

Acceptance criteria:

- Low-risk action bisa jalan langsung.
- Medium/high-risk action menunggu approval.
- Command tidak dikenal ditolak dengan alasan jelas.
- Semua eksekusi punya timeout, working directory, exit code, stdout/stderr, dan status.

### Milestone 4 - Logging Audit & Observability

Tujuan: semua aktivitas bisa dilacak untuk debugging dan audit.

Task:

- Tambahkan structured logging JSON lines di `logs/audit.jsonl`.
- Catat event:
  - `request_received`
  - `intent_parsed`
  - `plan_generated`
  - `approval_requested`
  - `approval_decision`
  - `execution_started`
  - `execution_finished`
  - `response_sent`
  - `error`
- Tambahkan `trace_id` untuk satu alur request end-to-end.
- Tambahkan command Telegram:
  - `/logs` untuk melihat audit terbaru.
  - `/last` untuk hasil eksekusi terakhir project aktif.
  - `/status` shortcut untuk health check.
- Tambahkan log rotation sederhana atau batas ukuran file.

Acceptance criteria:

- Setiap request punya trace yang lengkap.
- Error bisa dilihat tanpa akses shell langsung.
- `/last` menampilkan action terakhir beserta status dan ringkasannya.
- Log tidak membocorkan token Telegram atau secret environment.

### Milestone 5 - Context Memory

Tujuan: menyimpan PRD, task, keputusan, dan histori agar user tidak perlu menjelaskan ulang.

Task:

- Buat storage JSON awal:
  - `data/context/<project_id>/profile.json`
  - `data/context/<project_id>/decisions.jsonl`
  - `data/context/<project_id>/tasks.json`
  - `data/context/<project_id>/executions.jsonl`
  - `data/context/<project_id>/chat.jsonl`
- Tambahkan command Telegram:
  - `/remember <text>` untuk menyimpan catatan project.
  - `/decision <text>` untuk menyimpan keputusan.
  - `/tasks` untuk melihat task aktif.
  - `/task_add <text>` untuk menambahkan task.
  - `/task_done <id>` untuk menyelesaikan task.
  - `/context` untuk ringkasan memory project.
- Buat context injection untuk prompt Qwen:
  - project profile
  - keputusan terbaru
  - task aktif
  - hasil eksekusi terakhir
- Batasi jumlah context yang dikirim agar prompt tetap pendek.

Acceptance criteria:

- Memory bertahan setelah restart.
- Qwen bisa menjawab dengan mempertimbangkan context project.
- Task dan decision tersimpan per project.
- User bisa melihat, menambah, dan menyelesaikan task via Telegram.

### Milestone 6 - CLI Interface

Tujuan: menyediakan interface lokal selain Telegram.

Task:

- Buat entrypoint CLI, misalnya `python -m app.interfaces.cli`.
- Tambahkan command CLI:
  - `ai-agent status`
  - `ai-agent ask "<text>"`
  - `ai-agent run "<command>"`
  - `ai-agent project list`
  - `ai-agent project use <name>`
  - `ai-agent context show`
  - `ai-agent tasks list`
- Gunakan orchestrator yang sama dengan Telegram agar behavior konsisten.
- Tambahkan output mode:
  - human-readable
  - JSON untuk automation.

Acceptance criteria:

- CLI dan Telegram memakai service layer yang sama.
- CLI bisa dipakai tanpa menjalankan Telegram bot.
- CLI menghormati safety policy dan project context.
- Exit code CLI mencerminkan hasil eksekusi.

### Milestone 7 - Multi-Agent Skeleton

Tujuan: menyiapkan PM, Engineer, dan Reviewer agent sebagai workflow internal.

Task:

- Buat modul:
  - `app/agents/base.py`
  - `app/agents/pm.py`
  - `app/agents/engineer.py`
  - `app/agents/reviewer.py`
- Definisikan agent contract:
  - input context
  - output JSON
  - allowed tools
  - risk level
- PM Agent:
  - membuat PRD ringkas.
  - task breakdown.
  - acceptance criteria.
- Engineer Agent:
  - membuat plan perubahan kode.
  - memilih action yang valid.
  - menghasilkan command atau patch proposal.
- Reviewer Agent:
  - review output execution.
  - cek kualitas, risiko, dan test suggestion.
- Tambahkan command Telegram:
  - `/plan <goal>` untuk task breakdown.
  - `/review_last` untuk review hasil eksekusi terakhir.

Acceptance criteria:

- Agent belum perlu menjalankan perubahan kode otomatis penuh, tetapi bisa menghasilkan structured output yang valid.
- Semua agent memakai shared context project.
- Output agent tersimpan di memory.
- Workflow PM -> Engineer -> Reviewer bisa dijalankan untuk request sederhana.

### Milestone 8 - Deploy & Operational Commands

Tujuan: mendukung workflow deploy dasar dari Telegram secara aman.

Task:

- Tambahkan action deploy yang eksplisit:
  - `git_pull`
  - `docker_compose_ps`
  - `docker_compose_pull`
  - `docker_compose_build`
  - `docker_compose_up`
  - `docker_compose_restart`
  - `service_health_check`
- Tambahkan `/deploy` dengan approval wajib.
- Tambahkan `/health` untuk menjalankan server + Docker + app checks.
- Tambahkan rollback manual terbatas:
  - tampilkan commit sebelumnya.
  - siapkan command rollback sebagai plan high-risk.
  - wajib approval.
- Simpan hasil deploy ke execution history.

Acceptance criteria:

- `/deploy` menampilkan plan sebelum eksekusi.
- Deploy hanya berjalan di project yang punya konfigurasi deploy valid.
- Health check berjalan setelah deploy.
- User menerima ringkasan hasil deploy dan error jika ada.

## 5. Backlog Prioritas

### P0 - Harus Ada untuk MVP

- Refactor modul dari `app/bot.py`.
- Hapus token default hardcoded.
- Intent schema + validation.
- Action registry + safe executor.
- Project context berbasis JSON.
- Approval flow untuk command berisiko.
- Audit log JSON lines.
- Test parser, policy, runner, dan project store.

### P1 - Penting Setelah MVP

- CLI interface.
- Task memory dan decision memory.
- Plan generator multi-step.
- `/deploy` aman dengan health check.
- `/logs`, `/last`, `/context`, `/tasks`.
- Multi-agent skeleton PM, Engineer, Reviewer.

### P2 - Enhancement

- GitHub integration.
- Vector memory dengan Qdrant.
- Web dashboard.
- Multi-user role-based access yang lebih detail.
- Self-healing workflow.
- Scheduler/automation background job.

## 6. Struktur Direktori Target

```text
app/
  __init__.py
  config.py
  main.py
  ai/
    __init__.py
    qwen_client.py
  agents/
    __init__.py
    base.py
    pm.py
    engineer.py
    reviewer.py
  executor/
    __init__.py
    actions.py
    docker_actions.py
    git_actions.py
    runner.py
  interfaces/
    __init__.py
    telegram.py
    cli.py
  intents/
    __init__.py
    parser.py
    schemas.py
  memory/
    __init__.py
    store.py
    models.py
  orchestrator/
    __init__.py
    service.py
    plans.py
  safety/
    __init__.py
    policy.py
  telemetry/
    __init__.py
    audit.py
data/
  projects.json
  context/
logs/
  audit.jsonl
tests/
  test_intent_parser.py
  test_safety_policy.py
  test_project_store.py
  test_orchestrator.py
docs/
  plan/
    base-features.md
```

## 7. Data Model Awal

### Project

```json
{
  "id": "default",
  "name": "default",
  "root_path": ".",
  "description": "Default project",
  "created_at": "2026-05-02T00:00:00+07:00",
  "updated_at": "2026-05-02T00:00:00+07:00"
}
```

### Execution Record

```json
{
  "id": "uuid",
  "trace_id": "uuid",
  "project_id": "default",
  "source": "telegram",
  "user_id": "123456789",
  "intent": "docker_ps",
  "plan_id": "uuid",
  "status": "success",
  "started_at": "2026-05-02T00:00:00+07:00",
  "finished_at": "2026-05-02T00:00:02+07:00",
  "exit_code": 0,
  "summary": "3 containers are running"
}
```

### Task

```json
{
  "id": "TASK-001",
  "project_id": "default",
  "title": "Refactor bot into modular architecture",
  "status": "todo",
  "priority": "P0",
  "created_at": "2026-05-02T00:00:00+07:00",
  "completed_at": null
}
```

## 8. Safety Policy Awal

Command low-risk yang boleh langsung:

- `pwd`
- `whoami`
- `hostname`
- `uptime`
- `df -h`
- `du -sh`
- `free -h`
- `ps aux`
- `git status`
- `git log`
- `docker ps`
- `docker images`
- `docker stats --no-stream`
- `docker logs --tail`

Command medium-risk yang butuh approval:

- `git pull`
- `docker restart`
- `docker compose restart`
- `docker compose up -d`
- `docker compose build`
- `make restart`
- `make up`

Command high-risk yang ditolak atau butuh mode khusus:

- `rm`
- `mv` ke system path
- `chmod -R`
- `chown -R`
- `mkfs`
- `dd`
- `shutdown`
- `reboot`
- command dengan pipe/redirection berbahaya ke `/etc`, `/bin`, `/usr`, `/var/lib`, atau root filesystem.

## 9. Testing Plan

- Unit test:
  - local intent parser.
  - strict JSON parser fallback.
  - command policy allow/deny.
  - project store read/write.
  - action registry lookup.
- Integration test:
  - orchestrator request -> intent -> plan -> execution -> response.
  - approval pending -> approve -> execute.
  - project switch -> command runs in selected path.
- Manual test:
  - `/start`
  - `/whoami`
  - `/project_add`
  - `/project`
  - natural command: `cek status server`
  - natural command: `docker yang jalan apa aja`
  - risky command: `restart container app`
  - `/approve <plan_id>`
  - `/logs`
  - `/last`

## 10. Urutan Eksekusi yang Disarankan

1. Kerjakan Milestone 0 agar codebase siap berkembang.
2. Kerjakan Milestone 1 agar semua fitur berikutnya punya project context.
3. Kerjakan Milestone 2 dan 3 bersama karena intent, plan, dan safety saling bergantung.
4. Tambahkan Milestone 4 supaya debugging mudah sebelum fitur makin kompleks.
5. Tambahkan Milestone 5 untuk memory project dan task.
6. Tambahkan CLI pada Milestone 6 setelah orchestrator stabil.
7. Tambahkan skeleton multi-agent pada Milestone 7.
8. Tambahkan deploy workflow pada Milestone 8 setelah approval dan audit matang.

## 11. Definition of Done MVP

MVP dianggap selesai jika:

- Bot Telegram bisa menerima natural language command dan slash command utama.
- Setiap input menjadi intent dan plan yang tervalidasi.
- Aksi low-risk berjalan otomatis, aksi berisiko menunggu approval.
- User bisa mengelola project aktif.
- Context, task, decision, dan execution history tersimpan per project.
- Semua eksekusi tercatat dalam audit log.
- CLI bisa menjalankan status, ask, run, dan project command dasar.
- Test utama untuk parser, safety, memory, dan orchestrator tersedia.
- Dokumentasi README diperbarui dengan cara pakai fitur baru.
