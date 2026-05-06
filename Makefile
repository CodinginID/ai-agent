.PHONY: up down restart deploy logs logs-ollama logs-init status build shell pull-model clean \
        lint type-check test check install-dev db-upgrade db-downgrade release \
        dev

COMPOSE := $(shell docker compose version > /dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

# ── Development ──────────────────────────────────────────────────────────────

## Install dev dependencies (linting, type-check, testing)
install-dev:
	pip install -r requirements-dev.txt

## Jalankan aplikasi lokal — FastAPI + Telegram polling berjalan bersamaan
dev:
	./dev.sh

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

## Jalankan migration database ke versi terbaru
db-upgrade:
	alembic upgrade head

## Rollback satu migration database
db-downgrade:
	alembic downgrade -1

# ── Docker ───────────────────────────────────────────────────────────────────

## Jalankan semua service (build ulang jika ada perubahan kode)
up:
	$(COMPOSE) up -d --build

## Hentikan semua service
down:
	$(COMPOSE) down

## Restart hanya bot (tanpa restart Ollama)
restart:
	$(COMPOSE) restart bot

## Zero-downtime deploy: rebuild bot, infra tetap jalan, Caddy tidak direstart
deploy:
	$(COMPOSE) up -d --no-recreate redis ollama
	$(COMPOSE) up -d --build --no-deps bot
	@docker ps --format '{{.Names}}' | grep -q "^aiagent_caddy$$" || $(COMPOSE) up -d caddy

## Ikuti log bot secara realtime
logs:
	$(COMPOSE) logs -f bot

## Ikuti log Ollama secara realtime
logs-ollama:
	$(COMPOSE) logs -f ollama

## Ikuti log Caddy (reverse proxy) secara realtime
logs-caddy:
	$(COMPOSE) logs -f caddy

## Lihat log model init / model pull
logs-init:
	$(COMPOSE) logs -f ollama-init

## Lihat status semua container
status:
	$(COMPOSE) ps

## Build ulang image bot tanpa menjalankan
build:
	$(COMPOSE) build bot

## Masuk ke dalam container bot
shell:
	$(COMPOSE) exec bot sh

## Pull / update model AI (jalankan setelah ganti OLLAMA_MODEL di .env)
pull-model:
	$(COMPOSE) exec ollama ollama pull $$(grep OLLAMA_MODEL .env | cut -d= -f2 | tr -d ' ')

## Hapus semua container + volume (HATI-HATI: model AI ikut terhapus)
clean:
	$(COMPOSE) down -v

## Buat release baru — contoh: make release VERSION=0.2.0
release:
	@[ -n "$(VERSION)" ] || (echo "Gunakan: make release VERSION=x.y.z"; exit 1)
	make check
	git tag -a v$(VERSION) -m "Release v$(VERSION)"
	git push origin v$(VERSION)
	@echo "Tag v$(VERSION) dipush. GitHub Actions akan build & publish otomatis."
