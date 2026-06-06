#!/usr/bin/env bash
# ==============================================================================
#  Octopus CLI — LOCAL TEST Installer
#
#  Builds the octopus binary FROM SOURCE and installs it, instead of downloading
#  from GitHub Releases. Use this to test the full install -> run flow on a VPS
#  BEFORE cutting a public release (which needs a git tag + DNS).
#
#  Usage:
#     ./install-local.sh                       # build + install (auto URL/dir)
#     OCTOPUS_URL=http://127.0.0.1:8090 ./install-local.sh
#     OCTOPUS_INSTALL_DIR=~/.local/bin ./install-local.sh
#
#  Differences vs the published install.sh:
#     - Source of binary : local `go build` (this repo)  [vs GitHub Releases]
#     - Backend URL      : baked to OCTOPUS_URL          [vs repo var at CI time]
# ==============================================================================
set -euo pipefail

# ── Resolve repo paths ────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Config (overridable via env) ──────────────────────────────────────────────
VERSION="$(grep -E '^VERSION' Makefile | head -1 | sed -E 's/.*:= *//')"
VERSION="${OCTOPUS_VERSION:-${VERSION:-0.0.0-dev}}"
APP_URL="${OCTOPUS_URL:-http://127.0.0.1:8090}"
BIN_NAME="octopus"

# ── Colors ────────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'
  GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
else
  BOLD=''; DIM=''; RESET=''; GREEN=''; CYAN=''; RED=''; YELLOW=''
fi
info()  { printf "${CYAN}${BOLD}  →${RESET} %s\n" "$1" >&2; }
ok()    { printf "${GREEN}${BOLD}  ✓${RESET} %s\n" "$1" >&2; }
warn()  { printf "${YELLOW}${BOLD}  !${RESET} %s\n" "$1" >&2; }
fail()  { printf "\n${RED}${BOLD}  ✗ GAGAL:${RESET} %s\n\n" "$1" >&2; exit 1; }

printf "\n${CYAN}${BOLD}  ╭──────────────────────────────────────╮${RESET}\n" >&2
printf "${CYAN}${BOLD}  │   🐙  Octopus CLI — LOCAL Installer   │${RESET}\n" >&2
printf "${CYAN}${BOLD}  ╰──────────────────────────────────────╯${RESET}\n\n" >&2

# ── Step 1: Locate Go toolchain (PATH, then mise) ─────────────────────────────
info "Mencari Go toolchain..."
GO_BIN=""
if command -v go &>/dev/null; then
  GO_BIN="$(command -v go)"
elif command -v mise &>/dev/null && mise which go &>/dev/null; then
  GO_BIN="$(mise which go)"
else
  # Last resort: scan common mise install dir
  GO_BIN="$(find "$HOME/.local/share/mise/installs/go" -maxdepth 3 -name go -type f 2>/dev/null | sort -V | tail -1 || true)"
fi
[[ -n "$GO_BIN" && -x "$GO_BIN" ]] || fail "Go tidak ditemukan. Install Go atau jalankan: mise use go@1.24"
ok "Go: $("$GO_BIN" version | awk '{print $3}')"

# ── Step 2: Resolve install dir (writable first, sudo fallback) ───────────────
if [[ -n "${OCTOPUS_INSTALL_DIR:-}" ]]; then
  INSTALL_DIR="$OCTOPUS_INSTALL_DIR"
elif [[ -w "/usr/local/bin" ]]; then
  INSTALL_DIR="/usr/local/bin"
else
  INSTALL_DIR="$HOME/.local/bin"
fi
mkdir -p "$INSTALL_DIR"
ok "Install dir: $INSTALL_DIR"

# ── Step 3: Detect platform (informational) ───────────────────────────────────
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"; case "$ARCH" in x86_64) ARCH=amd64;; aarch64|arm64) ARCH=arm64;; esac
ok "Platform: ${OS}/${ARCH}"

# ── Step 4: Build from source ─────────────────────────────────────────────────
info "Build dari source (v${VERSION}, backend=${APP_URL})..."
LDFLAGS="-X main.defaultAppURL=${APP_URL} -X main.Version=${VERSION} -s -w"
TMP_BIN="$(mktemp)"
if ! "$GO_BIN" build -ldflags="$LDFLAGS" -o "$TMP_BIN" . 2>/tmp/octopus_build.log; then
  cat /tmp/octopus_build.log >&2
  rm -f "$TMP_BIN"
  fail "go build gagal (lihat log di atas)."
fi
ok "Build selesai"

# ── Step 5: Install ───────────────────────────────────────────────────────────
DEST="${INSTALL_DIR}/${BIN_NAME}"
chmod +x "$TMP_BIN"
if [[ -w "$INSTALL_DIR" ]]; then
  mv "$TMP_BIN" "$DEST"
else
  warn "Butuh sudo untuk menulis ke ${INSTALL_DIR}"
  sudo mv "$TMP_BIN" "$DEST"
fi
ok "Terpasang: ${BOLD}${DEST}${RESET}"

# ── Step 6: Verify binary ─────────────────────────────────────────────────────
if INSTALLED_VER="$("$DEST" --version 2>/dev/null | awk '{print $NF}')"; then
  ok "Verifikasi: octopus ${BOLD}${INSTALLED_VER}${RESET}"
else
  fail "Binary terpasang tapi gagal dijalankan."
fi

# ── Step 7: Backend reachability check ────────────────────────────────────────
info "Cek backend ${APP_URL}/health ..."
HC="$(curl -s -m5 -o /dev/null -w '%{http_code}' "${APP_URL}/health" 2>/dev/null || echo 000)"
if [[ "$HC" == "200" ]]; then
  ok "Backend sehat (HTTP 200)"
else
  warn "Backend belum merespons di ${APP_URL} (HTTP ${HC}) — pastikan container 'bot' jalan."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
printf "\n${GREEN}${BOLD}  ╭──────────────────────────────────────╮${RESET}\n" >&2
printf "${GREEN}${BOLD}  │   ✓  Install (lokal) selesai!         │${RESET}\n" >&2
printf "${GREEN}${BOLD}  ╰──────────────────────────────────────╯${RESET}\n\n" >&2
if ! command -v "$BIN_NAME" &>/dev/null; then
  printf "${YELLOW}  '$INSTALL_DIR' belum di PATH. Tambahkan:${RESET}\n" >&2
  printf "${BOLD}      export PATH=\"$INSTALL_DIR:\$PATH\"${RESET}\n\n" >&2
fi
printf "  Backend di-bake: ${BOLD}${APP_URL}${RESET}\n" >&2
printf "  Jalankan: ${BOLD}octopus${RESET}\n\n" >&2
