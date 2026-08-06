# Octopus

[![Release](https://img.shields.io/github/v/release/CodinginID/ai-agent)](https://github.com/CodinginID/ai-agent/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Octopus lets you monitor and control your server through natural language — from Telegram or a terminal TUI. Type what you want in plain text; Octopus figures out what to run and asks for confirmation before anything risky happens.

The Octopus backend is hosted centrally. You only need to install the CLI worker on your own machine.

---

## What you can do

**Server monitoring**
- Check server status, CPU load, memory, disk, and running processes

**Docker Compose**
- List running services, pull images, build, bring services up, restart a specific service

**Git**
- Status, diff, log, add, commit, push, pull, branch — all from chat

**Deploy**
- Run a full deploy (pull → build → up → health check) with one command
- Rollback to a previous commit if something goes wrong
- Health check any HTTP endpoint

**AI agents on your device**
- Octopus detects which AI CLIs you have installed (Codex, Claude, GLM) and reports their readiness
- Each device is registered separately — you can have multiple machines

**Safety first**
- Low-risk commands run immediately
- Medium and high-risk commands show a plan and wait for your `/approve` before executing
- Destructive patterns (force delete, overwrite system paths, fork bombs) are blocked outright

---

## Get started

### 1. Install the CLI on your machine

```bash
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/octopus-cli/install.sh | bash
```

### 2. Open Octopus

```bash
octopus
```

### 3. Log in

Inside the TUI, type `/login`. A QR code and link will appear — scan or open it to sign in with your Google account.

### 4. (Optional) Pair Telegram

Once logged in, type `/pair-telegram` to link your Telegram account so you can drive Octopus from chat too.

That's it. Your machine is now registered as a worker. Octopus starts detecting which AI CLIs you have installed and reports their status to the backend.

---

## Two ways to interact

### Telegram

Send a message directly to the Octopus bot:

```
cek status server
container mana yang running?
deploy sekarang
git status
cek memory
```

Slash commands:

| Command | What it does |
|---|---|
| `/start`, `/help` | Show available commands |
| `/approve <id>` | Approve a pending execution plan |
| `/reject <id>` | Reject a pending plan |
| `/agents` | Show AI agent status across your devices |
| `/devices` | List your registered worker devices |

### Terminal TUI

The same commands work inside the `octopus` terminal interface. Type naturally — the same way you would in Telegram.

**Self-upgrade:**

```bash
octopus upgrade
```

---

## Approval flow

For any operation that could change state — deploys, docker compose up, git push — Octopus shows the plan first:

```
📋 Execution Plan
─────────────────
1. git pull origin main
2. docker compose build
3. docker compose up -d --remove-orphans
4. health check → https://yourapp.com/health

Risiko: HIGH

Konfirmasi: /approve abc123
Batalkan:  /reject abc123
```

Low-risk reads (status, logs, git log) run immediately without confirmation.

---

## Multiple devices

You can register as many machines as you want. Each one runs the `octopus` worker independently. From Telegram, `/devices` shows all your connected machines and `/agents` shows which AI CLIs are ready on each one.

## Desktop App

Aplikasi desktop Wails (`octopus-desktop`) menyediakan antarmuka chat-first dan voice-first (Jarvis Mode) untuk mengontrol Octopus. Backend Go menangani koneksi SSE ke gateway dan subprocess STT/TTS lokal; frontend React/TS merender kartu visual per event.

**Dependency:** Go ≥ 1.25, [Wails CLI v2](https://wails.io/docs/gettingstarted/installation), `whisper-cli` (whisper.cpp) untuk STT, `piper` untuk TTS.

**Build & jalankan:**
```bash
# Instalasi Wails CLI (sekali)
go install github.com/wailsapp/wails/v2/cmd/wails@latest

# Build distribusi
cd octopus-desktop
wails build

# Mode pengembangan (hot-reload)
wails dev
```

Model STT/TTS dapat diunduh langsung dari menu Settings → "Unduh model" saat pertama kali buka aplikasi.

---

## Contributing

See [`CLAUDE.md`](CLAUDE.md) for architecture rules, naming conventions, and the Git workflow used in this project.

---

## Self-hosting

If you want to run your own Octopus backend instead of using the hosted service, see the instructions in [`install.sh`](install.sh).

---

## Monitoring & health

The backend exposes an aggregated health endpoint:

```
GET /health
```

Response:

```json
{
  "status": "ok",
  "version": "a1b2c3d",
  "dependencies": {
    "redis": "ok",
    "ollama": "ok",
    "database": "ok"
  }
}
```

`status` is `ok` only when every dependency reports `ok`. Any failure flips the top-level status to `degraded`.

**How to check status**

- Open `http://localhost:8000/health` in a browser (or `curl http://localhost:8000/health` from a terminal).
- A polling dashboard at `/dashboard` uses the same endpoint to show a real-time status widget for each dependency.
- The CLI worker shows connection state in its status bar (`TUI` → bottom bar) so you can see at a glance whether the gateway is reachable.

Probes are best-effort and time-boxed to 3 seconds each, so a slow Redis or Ollama will not block the response — it simply flips that dependency to `"down"`.

---

## Troubleshooting common issues

### Ollama tidak respond

1. Pastikan Ollama sudah berjalan: `ollama serve` atau cek service via `brew services list` / `systemctl status ollama`.
2. Cek model tersedia: `curl http://localhost:11434/api/tags`. Jika kosong, tarik model: `ollama pull qwen2.5`.
3. Jika Octopus men-report `"ollama": "down"` di `/health`, itu berarti probe ke port 11434 gagal — periksa firewall lokal atau bahwa Ollama listening di `0.0.0.0`, bukan hanya `127.0.0.1`.
4. Restart adapter di backend tanpa me-restart service keseluruhan: gunakan `/restart-adapter ollama` dari TUI atau Telegram.

### Redis tidak connect

1. Cek Redis berjalan: `redis-cli ping` harus mengembalikan `PONG`.
2. Pastikan `REDIS_URL` di `.env` (atau environment) mengarah ke alamat yang benar. Default: `redis://localhost:6379`.
3. Jika backend berjalan di Docker dan Redis di host, gunakan `host.docker.internal:6379` sebagai hostname.
4. Error yang sering muncul — `ConnectionRefusedError` atau `TimeoutError` — berarti backend tidak bisa menjangkau Redis sama sekali, bukan masalah auth.

### SQLite corruption

SQLite digunakan oleh worker CLI untuk menyimpan state lokal. Jika kamu melihat error seperti `database disk image is malformed` atau `UNIQUE constraint failed`:

1. **Jangan** langsung hapus file database tanpa backup.
2. Coba repair: `sqlite3 ~/.config/octopus/worker.db "PRAGMA integrity_check;"`
3. Jika integrity check gagal, backup dan inisialisasi ulang:
   ```bash
   mv ~/.config/octopus/worker.db ~/.config/octopus/worker.db.bak
   octopus reset
   ```
4. Untuk mencegah korupsi di masa depan, pastikan proses Octopus tidak di-force-kill saat menulis — selalu gunakan `/exit` atau `Ctrl-C` untuk menghentikan TUI.

### Worker tidak muncul di `/devices`

- Pastikan `octopus` worker sedang berjalan di mesin target.
- Cek koneksi ke gateway: `octopus status` — harus menunjukkan `connected`.
- Jika stuck di `connecting...`, periksa apakah API key valid dan URL gateway benar (cek di dashboard settings).

---

## Links

| Resource | Description |
|---|---|
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Panduan kontribusi: setup lokal, workflow Git, cara mengajukan PR |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | Dokumentasi pengembangan: arsitektur detail, testing, deployment |
| [`CLAUDE.md`](CLAUDE.md) | Aturan arsitektur hexagonal, konvensi penamaan, dan Git workflow |
| [`LICENSE`](LICENSE) | Lisensi MIT |

---

## License

[MIT](LICENSE)
