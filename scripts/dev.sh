#!/usr/bin/env bash
# Jalankan AI Agent dalam mode development.
#
# Default: backend di Docker (bot + ollama), TUI client di host.
# Mode "local": backend uvicorn lokal (--reload) di terminal terpisah, TUI di sini.
#
# Pemakaian:
#   ./dev.sh           # docker mode (default)
#   ./dev.sh local     # local mode — backend & TUI manual di 2 terminal
#   ./dev.sh stop      # docker compose stop semua service

set -euo pipefail

cd "$(dirname "$0")"

MODE="${1:-docker}"

# ── Load .env ──────────────────────────────────────────────────────────────
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

# ── Aktifkan virtualenv kalau ada ──────────────────────────────────────────
if [ -d ".venv" ]; then
    # shellcheck disable=SC1091
    . .venv/bin/activate
fi

# ── docker compose / docker-compose ────────────────────────────────────────
DC=""
if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
fi

case "$MODE" in
    docker)
        if [ -z "$DC" ]; then
            echo "Docker tidak terdeteksi. Pakai './dev.sh local' atau install Docker."
            exit 1
        fi
        echo "▸ Build & up backend (bot + ollama) di Docker…"
        $DC up -d --build bot
        echo "▸ Tunggu backend healthy…"
        for i in $(seq 1 30); do
            status=$($DC ps --format json bot 2>/dev/null | grep -oE '"Health":"[a-z]+"' | head -1 | cut -d'"' -f4)
            if [ "$status" = "healthy" ]; then
                echo "  backend healthy."
                break
            fi
            sleep 2
            if [ "$i" = "30" ]; then
                echo "  backend belum healthy setelah 60s — jalankan TUI saja, cek '/status'."
            fi
        done
        echo "▸ Buka TUI client (Ctrl-D atau /quit untuk keluar; container tetap running)."
        echo
        export DEV=1
        python -m app.tui
        echo
        echo "TUI exit. Container backend masih jalan. './dev.sh stop' untuk matikan."
        ;;

    local)
        export DEV=1
        echo "▸ Local mode. Buka 2 terminal:"
        echo "    Terminal 1: python -m app.main           # backend uvicorn --reload"
        echo "    Terminal 2: python -m app.tui            # TUI client"
        echo
        echo "Atau tekan Enter untuk start backend di terminal ini (TUI dijalankan manual)."
        read -r _
        exec python -m app.main
        ;;

    stop)
        if [ -z "$DC" ]; then
            echo "Docker tidak terdeteksi."
            exit 1
        fi
        $DC stop
        ;;

    *)
        echo "Usage: ./dev.sh [docker|local|stop]"
        exit 1
        ;;
esac
