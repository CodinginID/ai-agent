.PHONY: up down restart deploy deploy-staged rollback health-check canary-deploy \
        logs logs-ollama logs-init status build shell pull-model clean \
        lint type-check test check install-dev db-upgrade db-downgrade release \
        dev

COMPOSE := $(shell docker compose version > /dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

# ── Development ──────────────────────────────────────────────────────────────

## Install dev dependencies (linting, type-check, testing)
install-dev:
	pip install -r backend/requirements-dev.txt

## Jalankan aplikasi lokal — FastAPI + Telegram polling berjalan bersamaan
dev:
	./scripts/dev.sh

## Jalankan linter (ruff)
lint:
	ruff check backend/app/ backend/tests/

## Jalankan type checker (mypy)
type-check:
	mypy backend/app/

## Jalankan semua test
test:
	pytest backend/tests/ -v

## Jalankan lint + type-check + test sekaligus (wajib sebelum push)
check: lint type-check test

## Jalankan migration database ke versi terbaru
db-upgrade:
	cd backend && alembic upgrade head

## Rollback satu migration database
db-downgrade:
	cd backend && alembic downgrade -1

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

## Deploy ke staging: build ulang (tanpa cache) + deploy + health check,
## rollback otomatis jika health check gagal. Gunakan APP_VERSION=staging-x.y.z
## sebelum menjalankan agar /health melaporkan versi staging yang benar.
deploy-staged:
	@echo "[staged] Capture HEAD pra-deploy..."
	@PRE_COMMIT=$$(git rev-parse HEAD) && echo "pre_deploy_commit: $$PRE_COMMIT"
	@PRE_COMMIT=$$(git rev-parse HEAD) && \
	$(COMPOSE) up -d --build --no-cache --no-deps bot && \
	echo "[staged] Bot rebuilt (no-cache) + infra tidak disentuh." && \
	$(MAKE) --no-print-directory health-check || \
	(echo "[staged] Health check gagal — rollback ke $$PRE_COMMIT..." && \
	 git checkout $$PRE_COMMIT -- . && \
	 docker compose up -d --no-deps bot && \
	 echo "[staged] Rollback selesai. Jalankan 'make health-check' untuk verifikasi.")

## Rollback ke versi terakhir yang terverifikasi sehat:
##   1. Restore code ke last-known-good commit (yang ditandai di .rollback-marker)
##   2. Drop semua container, hapus network lama, dan jalankan ulang
##   3. Restart services (bot hanya, infra tetap)
##   4. Jalankan health check pasca-rollback
##   5. Jika database perlu di-restore dari backup, jalankan secara manual:
##      psql "$$DATABASE_URL" -f backup_YYYYMMDD.sql
rollback:
	@if [ ! -f .rollback-marker ]; then \
		echo "❌ .rollback-marker tidak ditemukan — tidak ada target rollback."; \
		exit 1; \
	fi
	@PREV=$$(cat .rollback-marker) && \
	echo "[rollback] Kembali ke commit $$PREV..." && \
	git checkout $$PREV -- . && \
	echo "[rollback] Container di-reset..." && \
	$(COMPOSE) down && \
	$(COMPOSE) up -d --remove-orphans && \
	$(MAKE) --no-print-directory health-check && \
	echo "[rollback] Rollback sukses." || \
	(echo "[rollback] Rollback tidak tuntas — cek log dengan 'make logs'."; exit 1)

## Health check: hit GET /health lalu verifikasi status == "ok".
## Exit 1 jika status == "degraded" (ada dependency yang down).
## Port default 8090 (Caddy host port); bisa di-override dengan PORT=.
health-check:
	@PORT=$${PORT:-8090}; \
	echo "[health] GET http://127.0.0.1:$$PORT/health ..."; \
	RESP=$$(curl -sfS --max-time 10 http://127.0.0.1:$$PORT/health); \
	STATUS=$$(echo "$$RESP" | grep -o '"status":"[^"]*"' | head -1 | sed 's/.*"status":"//; s/".*//'); \
	if [ "$$STATUS" = "ok" ]; then \
		echo "✅ /health status = ok"; \
		echo "$$RESP" | head -5; \
	else \
		echo "❌ /health status = $${STATUS:-unknown} — service DEGRADED."; \
		echo "$$RESP"; \
		exit 1; \
	fi

## Canary deploy: deploy ke 10% traffic dulu (simulasi tanpa load balancer),
## monitor error rate 5 menit melalui health endpoint. Jika status != "ok" >1%
## dari total probe, rollback otomatis ke last-known-good commit.
##
## Cara kerja: karena tidak ada load balancer di proyek ini, canary di-simulasikan
## dengan cara: build + deploy bot baru + monitor /health setiap 15 detik selama
## 5 menit. Jika seluruh probe OK, deploy dianggap sukses dan marker rollback
## di-update ke HEAD. Jika ada probe gagal, rollback dilakukan.
canary-deploy:
	@echo "[canary] 10% traffic deployment — monitoring 5 menit..."
	@PREV=$${PREV:-$$(cat .rollback-marker 2>/dev/null || git rev-parse HEAD)}; \
	FAILED=0; \
	TOTAL=0; \
	echo "[canary] Monitor /health setiap 15 detik selama 5 menit..."; \
	for i in $$(seq 1 20); do \
		sleep 15; \
		TOTAL=$$((TOTAL + 1)); \
		PORT=$${PORT:-8090}; \
		if RESP=$$(curl -sfS --max-time 8 http://127.0.0.1:$$PORT/health 2>/dev/null); then \
			S=$$(echo "$$RESP" | grep -o '"status":"[^"]*"' | head -1 | sed 's/.*"status":"//; s/".*//'); \
			if [ "$$S" != "ok" ]; then FAILED=$$((FAILED + 1)); fi; \
		else \
			FAILED=$$((FAILED + 1)); \
		fi; \
	done; \
	RATE=$$(awk "BEGIN {printf \"%.1f\", ($$FAILED / $$TOTAL) * 100}"); \
	echo "[canary] Error rate: $${FAILED}/$$TOTAL ($$RATE%)"; \
	THRESHOLD="1.0"; \
	BAD=$$(awk "BEGIN {print ($$RATE > $$THRESHOLD) ? 1 : 0}"); \
	if [ "$$BAD" = "1" ]; then \
		echo "[canary] Error rate $$RATE% > $$THRESHOLD% — auto-rollback ke $$PREV"; \
		git checkout $$PREV -- .; \
		$(COMPOSE) up -d --no-deps bot; \
		echo "[canary] Rollback selesai."; \
		exit 1; \
	else \
		echo "[canary] Error rate $$RATE% <= $$THRESHOLD% — canary promoted."; \
		git rev-parse HEAD > .rollback-marker; \
		echo "[canary] .rollback-marker di-update ke HEAD."; \
	fi

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
