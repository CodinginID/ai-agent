#!/usr/bin/env bash
# Jalankan aplikasi di mode development.
# Wizard setup otomatis jalan jika TELEGRAM_BOT_TOKEN belum dikonfigurasi.
#
# Usage:
#   make dev              → polling mode (default)
#   make dev MODE=webhook → webhook mode dengan uvicorn --reload

set -euo pipefail

cd "$(dirname "$0")"

# Load .env jika ada
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

# Aktifkan virtualenv jika ada
if [ -d ".venv" ]; then
    # shellcheck disable=SC1091
    . .venv/bin/activate
fi

export DEV=1
export MODE="${MODE:-polling}"

exec python -m app.main
