#!/usr/bin/env bash
# ==============================================================
#  Octopus — Backup & Restore (portabilitas pindah server)
#
#  Tujuan: pindah server TANPA setup manual satu per satu.
#  Backup membungkus SEMUA state (.env, database, Redis, volume
#  manifest) jadi satu tarball. Restore memulihkannya di server baru.
#
#  Pakai:
#    ./scripts/octopus-backup.sh backup            # buat octopus-backup-<ts>.tar.gz
#    ./scripts/octopus-backup.sh restore <file>    # pulihkan dari tarball
#
#  Pindah server (ringkas):
#    server lama : ./scripts/octopus-backup.sh backup
#    scp octopus-backup-*.tar.gz user@server-baru:~/ai-agent/
#    server baru : curl -fsSL .../install.sh | bash   (sekali, untuk docker+image)
#                  ./scripts/octopus-backup.sh restore octopus-backup-*.tar.gz
# ==============================================================
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root
ROOT="$(pwd)"
TS="$(date +%Y%m%d-%H%M%S)"
COMPOSE="docker compose"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
die()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Apakah DATABASE_URL menunjuk Postgres?
_is_postgres() {
    grep -qE '^DATABASE_URL=postgresql' "$ROOT/.env" 2>/dev/null
}

backup() {
    local stage="$ROOT/.backup-stage-$TS"
    local out="$ROOT/octopus-backup-$TS.tar.gz"
    mkdir -p "$stage"
    info "Membuat backup → $(basename "$out")"

    # 1. .env (kredensial + config) — inti portabilitas
    [[ -f "$ROOT/.env" ]] && cp "$ROOT/.env" "$stage/.env" && ok ".env"

    # 2. Database
    if _is_postgres; then
        info "Postgres terdeteksi — pg_dump..."
        $COMPOSE exec -T postgres pg_dumpall -U "${POSTGRES_USER:-octopus}" \
            > "$stage/postgres.sql" 2>/dev/null \
            && ok "postgres.sql" || warn "pg_dump gagal (service jalan?)"
    else
        info "SQLite terdeteksi — copy file DB..."
        if [[ -f "$ROOT/data/control_plane.sqlite3" ]]; then
            cp "$ROOT/data/control_plane.sqlite3" "$stage/control_plane.sqlite3"
            ok "control_plane.sqlite3"
        else
            warn "file SQLite belum ada (bot belum pernah jalan?)"
        fi
    fi

    # 3. Redis (worker state, job store, task events) — best-effort
    if $COMPOSE ps --status running 2>/dev/null | grep -q redis; then
        $COMPOSE exec -T redis redis-cli SAVE >/dev/null 2>&1 || true
        $COMPOSE cp redis:/data/dump.rdb "$stage/redis-dump.rdb" 2>/dev/null \
            && ok "redis-dump.rdb" || warn "redis dump dilewati"
    fi

    # 4. Manifest (untuk verifikasi di sisi restore)
    {
        echo "created_at=$TS"
        echo "db_mode=$(_is_postgres && echo postgres || echo sqlite)"
        echo "git_head=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    } > "$stage/MANIFEST"
    ok "MANIFEST"

    tar -czf "$out" -C "$stage" .
    rm -rf "$stage"
    ok "Backup selesai: $out"
    echo ""
    echo -e "  Pindah ke server baru:"
    echo -e "    ${YELLOW}scp $(basename "$out") user@server-baru:~/ai-agent/${NC}"
    echo -e "    ${YELLOW}./scripts/octopus-backup.sh restore $(basename "$out")${NC}"
}

restore() {
    local file="${1:-}"
    [[ -n "$file" && -f "$file" ]] || die "Pakai: $0 restore <file.tar.gz>"
    local stage="$ROOT/.restore-stage-$TS"
    mkdir -p "$stage"
    tar -xzf "$file" -C "$stage"
    info "Manifest:"; cat "$stage/MANIFEST" 2>/dev/null | sed 's/^/    /'

    # 1. .env
    if [[ -f "$stage/.env" ]]; then
        [[ -f "$ROOT/.env" ]] && cp "$ROOT/.env" "$ROOT/.env.before-restore-$TS"
        cp "$stage/.env" "$ROOT/.env"
        ok ".env dipulihkan (backup lama → .env.before-restore-$TS)"
    fi

    local db_mode; db_mode="$(grep -oP '(?<=^db_mode=).*' "$stage/MANIFEST" 2>/dev/null || echo sqlite)"

    # 2. Database — start service yang relevan dulu
    if [[ "$db_mode" == "postgres" ]]; then
        info "Menyalakan Postgres untuk restore..."
        $COMPOSE --profile postgres up -d postgres
        sleep 8
        if [[ -f "$stage/postgres.sql" ]]; then
            $COMPOSE exec -T postgres psql -U "${POSTGRES_USER:-octopus}" \
                < "$stage/postgres.sql" >/dev/null 2>&1 \
                && ok "postgres restored" || warn "psql restore ada warning (cek manual)"
        fi
    else
        mkdir -p "$ROOT/data"
        if [[ -f "$stage/control_plane.sqlite3" ]]; then
            cp "$stage/control_plane.sqlite3" "$ROOT/data/control_plane.sqlite3"
            ok "SQLite DB dipulihkan"
        fi
    fi

    # 3. Redis
    if [[ -f "$stage/redis-dump.rdb" ]]; then
        $COMPOSE up -d redis; sleep 3
        $COMPOSE cp "$stage/redis-dump.rdb" redis:/data/dump.rdb 2>/dev/null \
            && $COMPOSE restart redis && ok "Redis dipulihkan" || warn "Redis restore dilewati"
    fi

    rm -rf "$stage"
    ok "Restore selesai."
    echo ""
    echo -e "  Jalankan semua service:"
    if [[ "$db_mode" == "postgres" ]]; then
        echo -e "    ${YELLOW}$COMPOSE --profile postgres --profile telegram up -d${NC}"
    else
        echo -e "    ${YELLOW}$COMPOSE --profile telegram up -d${NC}"
    fi
}

case "${1:-}" in
    backup)  backup ;;
    restore) restore "${2:-}" ;;
    *) die "Pakai: $0 {backup|restore <file>}" ;;
esac
