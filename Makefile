.PHONY: up down restart logs status build shell pull-model clean \
        lint type-check test check install-dev

# ── Development ──────────────────────────────────────────────────────────────

## Install dev dependencies (linting, type-check, testing)
install-dev:
	pip install -r requirements-dev.txt

## Jalankan linter (ruff)
lint:
	ruff check app/ tests/

## Jalankan type checker (mypy)
type-check:
	mypy app/

## Jalankan semua test
test:
	pytest tests/ -v

## Jalankan lint + type-check + test sekaligus (wajib sebelum push)
check: lint type-check test

# ── Docker ───────────────────────────────────────────────────────────────────

## Jalankan semua service (build ulang jika ada perubahan kode)
up:
	docker compose up -d --build

## Hentikan semua service
down:
	docker compose down

## Restart hanya bot (tanpa restart Ollama)
restart:
	docker compose restart bot

## Ikuti log bot secara realtime
logs:
	docker compose logs -f bot

## Lihat status semua container
status:
	docker compose ps

## Build ulang image bot tanpa menjalankan
build:
	docker compose build bot

## Masuk ke dalam container bot
shell:
	docker compose exec bot sh

## Pull / update model AI (jalankan setelah ganti OLLAMA_MODEL di .env)
pull-model:
	docker compose exec ollama ollama pull $$(grep OLLAMA_MODEL .env | cut -d= -f2 | tr -d ' ')

## Hapus semua container + volume (HATI-HATI: model AI ikut terhapus)
clean:
	docker compose down -v
