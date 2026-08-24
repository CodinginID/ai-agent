# Panduan Pengembangan Lokal

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Menjalankan

**Mode lokal** (backend uvicorn + TUI, tanpa Docker):

```bash
# Terminal 1: backend
python -m app.main

# Terminal 2: TUI client
python -m app.tui
```

**Mode Docker** (default, backend di container):

```bash
make dev
# atau
./dev.sh
```

Untuk keluar dari TUI tanpa menghentikan container: `Ctrl-D` atau ketik `/quit`.
Matikan semua container dengan `make stop` atau `./dev.sh stop`.

## Testing

```bash
pytest tests/ -v
```

## Kualitas Kode

```bash
# Linting
ruff check app/ tests/

# Type checking
mypy app/

# Semua sekaligus (wajib sebelum push)
make check
```

## Debugging

- Set `DEV=1` (otomatis oleh `dev.sh`) untuk auto-reload uvicorn pada perubahan kode.
- Log backend tersimpan di `data/server.log` (rota, max 5 MB x 3 backup).
- Cek `/status` di TUI atau `make logs` untuk melihat log container secara realtime.
- Masuk ke container bot: `make shell`.

## Database

- Default: SQLite di `data/control_plane.sqlite3`.
- Migrate ke versi terbaru:

```bash
alembic upgrade head
```

- Rollback satu versi:

```bash
alembic downgrade -1
```

## Struktur Proyek

```
app/
  main.py          # entrypoint: uvicorn + alembic upgrade
  bot.py           # Telegram bot polling
  config.py        # environment variables & settings
  composition.py   # orchestrator composition
  interfaces/      # FastAPI gateway
  domain/          # entities & use cases (zero external deps)
  ports/           # Protocol/abstract interfaces
  adapters/        # implementasi port (Ollama, Telegram, SQLite, Redis, dll)
  actions/         # executable actions (server, docker, git, dll)
  handlers/        # message handlers Telegram
  intents/         # intent classification
  orchestrator/    # task orchestration
  executor/        # task execution engine
  agents/          # AI agent definitions
  memory/          # memory & context store
  tui/             # terminal user interface
  safety/          # safety policy
  setup/           # setup wizard

tests/             # unit & integration tests
data/              # SQLite DB, chat history, project metadata
alembic/           # database migrations
```
