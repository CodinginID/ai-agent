# Deploy & Pindah Server — Octopus

Panduan ini menjawab satu pertanyaan: **bagaimana pindah server tanpa setup manual satu per satu.**

Prinsipnya: semua *state* (kredensial, database, memori RAG, worker state) hidup di
**`.env` + Docker volumes**. Pindah server = backup state → copy satu file →
restore. Kode & image ditarik otomatis dari GHCR.

---

## 1. Instalasi pertama (server baru, dari nol)

```bash
# Satu baris — install Docker image + config + jalankan
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/install.sh | bash
```

Installer akan: cek Docker, download `docker-compose.yml` + `.env.example`,
tanya Telegram token, pull image, lalu `docker compose up -d`.

### Isi konfigurasi penting di `.env`

| Variabel | Untuk apa | Wajib? |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | bot Telegram | ya |
| `GITHUB_TOKEN` + `GITHUB_REPO` | orchestrator `/task` (PM→Issue→Close) | untuk `/task` |
| `DATABASE_URL` | SQLite (default) atau Postgres | default OK |
| `RAG_ENABLED` / `EMBEDDER_BACKEND` | memori semantik | default OK |
| `ADMIN_TOKEN` | admin API | opsional |

`GITHUB_TOKEN`: bikin di GitHub → Settings → Developer settings → Personal
access token, scope **`repo`** (classic) atau **Issues: read/write** (fine-grained).
Tanpa ini `/task` balas `503 task runner unavailable`.

---

## 2. Mode database — pilih satu

### SQLite (default, zero-setup)
Cukup untuk single-node. **Catatan:** RAG pakai in-memory store → knowledge
hilang saat restart. Tidak perlu konfigurasi apa pun.

### Postgres + pgvector (RAG persisten, disarankan untuk produksi)
RAG (memori semantik) bertahan lintas restart. Aktifkan profil bawaan:

```bash
# 1. Aktifkan & jalankan Postgres
docker compose --profile postgres up -d

# 2. Ganti dua baris ini di .env (password = POSTGRES_PASSWORD):
DATABASE_URL=postgresql+psycopg://octopus:octopus@postgres:5432/octopus
DATABASE_MIGRATION_URL=postgresql+psycopg://octopus:octopus@postgres:5432/octopus

# 3. Restart bot — migrasi alembic (termasuk pgvector) jalan otomatis saat start
docker compose up -d bot
```

Migrasi `CREATE EXTENSION vector` + tabel `knowledge_chunks` (HNSW cosine index)
otomatis di Postgres, dan **di-skip otomatis di SQLite** — jadi aman bolak-balik.

---

## 3. Pindah server — TANPA setup manual ⭐

Inti dari portabilitas. Tiga langkah.

### Di server LAMA
```bash
cd ~/ai-agent
./scripts/octopus-backup.sh backup
# → menghasilkan octopus-backup-<timestamp>.tar.gz
#   berisi: .env + database (SQLite file / pg_dump) + Redis dump + manifest
```

### Pindahkan
```bash
scp octopus-backup-*.tar.gz user@server-baru:~/ai-agent/
```

### Di server BARU
```bash
# 1. Install sekali (Docker + image + compose) — JANGAN isi token, akan ditimpa
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/install.sh | bash

# 2. Pulihkan semua state dari backup
cd ~/ai-agent
./scripts/octopus-backup.sh restore octopus-backup-*.tar.gz

# 3. Jalankan (restore akan kasih tahu perintah persisnya)
docker compose --profile telegram up -d
#   + tambah --profile postgres kalau pakai Postgres
```

Selesai. `.env`, database, dan memori RAG identik dengan server lama. Tidak ada
setup token / config manual yang diulang.

---

## 4. Update versi (tanpa kehilangan data)

```bash
cd ~/ai-agent
docker compose pull          # tarik image terbaru dari GHCR
docker compose up -d         # recreate container, volume (data) tetap
```

Volume (`aiagent_postgres_data`, `aiagent_redis_data`, dst.) tidak ikut terhapus
saat `up -d` / `pull`. Hanya `docker compose down -v` yang menghapus volume —
**jangan pakai `-v`** kecuali memang mau reset total.

---

## 5. Pantau saat testing

```bash
docker compose logs -f bot                      # semua log bot
docker compose logs -f bot | grep octopus.tasks # khusus lifecycle /task
# Board task (JSON): GET /tasks via Caddy
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8090/tasks/
```

Log task terstruktur: `[ROLE][TASK_ID][STATUS] pesan` — gampang di-`grep` per task.

---

## 6. Checklist go-live

- [ ] `.env`: `TELEGRAM_BOT_TOKEN`, `GITHUB_TOKEN`, `GITHUB_REPO` terisi
- [ ] (opsional) Postgres: profil aktif + `DATABASE_URL` Postgres + restart bot
- [ ] `docker compose ps` → semua service `healthy`
- [ ] `curl localhost:8090/health` → `{"status":"ok"}`
- [ ] Telegram: `/start` → pair, lalu `/task <deskripsi>` → cek issue dibuat di `GITHUB_REPO`
- [ ] `docker compose logs -f bot | grep octopus.tasks` → lihat lifecycle jalan
