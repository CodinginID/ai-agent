#!/usr/bin/env bash
set -euo pipefail

GITHUB_REPO="codinginid/ai-agent"
INSTALL_DIR="${OCTOPUS_INSTALL_DIR:-/usr/local/bin}"
BIN_NAME="octopus"

# ── Colors (hanya kalau terminal support) ─────────────────────────────────────
if [[ -t 1 ]]; then
  BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'
  GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
else
  BOLD=''; DIM=''; RESET=''; GREEN=''; CYAN=''; RED=''; YELLOW=''
fi

# Helpers — semua output ke stderr supaya tidak terpotong pipe
info()  { printf "${CYAN}${BOLD}  →${RESET} %s\n" "$1" >&2; }
ok()    { printf "${GREEN}${BOLD}  ✓${RESET} %s\n" "$1" >&2; }
warn()  { printf "${YELLOW}${BOLD}  !${RESET} %s\n" "$1" >&2; }
fail()  {
  printf "\n${RED}${BOLD}  ╭─────────────────────────────────────────╮${RESET}\n" >&2
  printf "${RED}${BOLD}  │  ✗  INSTALASI GAGAL                     │${RESET}\n" >&2
  printf "${RED}${BOLD}  ╰─────────────────────────────────────────╯${RESET}\n\n" >&2
  echo -e "${RED}  $1${RESET}\n" >&2
  exit 1
}

# ── Banner ────────────────────────────────────────────────────────────────────
printf "\n" >&2
printf "${CYAN}${BOLD}  ╭─────────────────────────────────╮${RESET}\n" >&2
printf "${CYAN}${BOLD}  │   🐙  Octopus CLI Installer     │${RESET}\n" >&2
printf "${CYAN}${BOLD}  ╰─────────────────────────────────╯${RESET}\n" >&2
printf "\n" >&2

# ── Step 1: Resolve version ───────────────────────────────────────────────────
if [[ -n "${OCTOPUS_VERSION:-}" ]]; then
  VERSION="$OCTOPUS_VERSION"
  ok "Version: v${VERSION} (dari OCTOPUS_VERSION)"
else
  info "Mengecek versi terbaru dari GitHub..."
  HTTP_CODE=$(curl -o /tmp/_octopus_api.json -w "%{http_code}" -fsSL \
    "https://api.github.com/repos/${GITHUB_REPO}/releases/latest" 2>/dev/null || echo "000")

  if [[ "$HTTP_CODE" == "200" ]]; then
    VERSION=$(grep '"tag_name"' /tmp/_octopus_api.json | head -1 \
      | sed 's/.*"tag_name": *"\(.*\)".*/\1/' | sed 's/^v//')
    rm -f /tmp/_octopus_api.json
  else
    rm -f /tmp/_octopus_api.json
    fail "Belum ada release yang tersedia (HTTP ${HTTP_CODE}).\n\n  Coba set versi manual:\n  OCTOPUS_VERSION=0.2.0 curl -fsSL https://raw.githubusercontent.com/${GITHUB_REPO}/main/octopus-cli/install.sh | bash"
  fi

  if [[ -z "$VERSION" ]]; then
    fail "Gagal membaca versi dari GitHub.\n\n  Coba: OCTOPUS_VERSION=0.2.0 curl -fsSL ... | bash"
  fi

  ok "Versi terbaru: ${BOLD}v${VERSION}${RESET}"
fi

# ── Step 2: Detect platform ───────────────────────────────────────────────────
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in
  x86_64)         ARCH="amd64" ;;
  aarch64|arm64)  ARCH="arm64" ;;
  *) fail "Arsitektur tidak didukung: $ARCH" ;;
esac

if [[ "$OS" == "windows"* ]]; then
  BINARY_NAME="octopus-windows-amd64.exe"
else
  BINARY_NAME="octopus-${OS}-${ARCH}"
fi

ok "Platform: ${OS}/${ARCH}"

# ── Step 3: Download ──────────────────────────────────────────────────────────
DOWNLOAD_URL="https://github.com/${GITHUB_REPO}/releases/download/v${VERSION}/${BINARY_NAME}"
info "Mengunduh dari GitHub Releases..."
printf "  ${DIM}%s${RESET}\n" "$DOWNLOAD_URL" >&2

TMP=$(mktemp)
HTTP_CODE=$(curl -w "%{http_code}" -fsSL "$DOWNLOAD_URL" -o "$TMP" 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" != "200" ]]; then
  rm -f "$TMP"
  fail "Download gagal (HTTP ${HTTP_CODE}).\n  URL: $DOWNLOAD_URL\n\n  Cek: https://github.com/${GITHUB_REPO}/releases"
fi
chmod +x "$TMP"
ok "Download selesai"

# ── Step 4: Install ───────────────────────────────────────────────────────────
info "Menginstall ke ${INSTALL_DIR}..."
if [ -w "$INSTALL_DIR" ]; then
  mv "$TMP" "${INSTALL_DIR}/${BIN_NAME}"
else
  warn "Butuh sudo untuk install ke ${INSTALL_DIR}"
  sudo mv "$TMP" "${INSTALL_DIR}/${BIN_NAME}"
fi
ok "Binary tersimpan di: ${BOLD}${INSTALL_DIR}/${BIN_NAME}${RESET}"

# ── Step 5: Verify ────────────────────────────────────────────────────────────
info "Memverifikasi instalasi..."
if INSTALLED_VER=$("${INSTALL_DIR}/${BIN_NAME}" --version 2>/dev/null | awk '{print $NF}'); then
  ok "Verifikasi OK — octopus ${BOLD}${INSTALLED_VER}${RESET}"
else
  warn "Binary terinstall tapi gagal dijalankan (mungkin masalah arch/permission)"
fi

# ── Cek apakah langsung bisa dipanggil ────────────────────────────────────────
NEEDS_HASH=false
if ! command -v "$BIN_NAME" &>/dev/null; then
  NEEDS_HASH=true
fi

# ── Done ──────────────────────────────────────────────────────────────────────
printf "\n" >&2
printf "${GREEN}${BOLD}  ╭─────────────────────────────────────────╮${RESET}\n" >&2
printf "${GREEN}${BOLD}  │   ✓  Instalasi selesai!                 │${RESET}\n" >&2
printf "${GREEN}${BOLD}  ╰─────────────────────────────────────────╯${RESET}\n" >&2
printf "\n" >&2

if [[ "$NEEDS_HASH" == "true" ]]; then
  printf "${YELLOW}${BOLD}  Jalankan perintah ini supaya shell mengenali 'octopus':${RESET}\n\n" >&2
  printf "${BOLD}      hash -r && octopus${RESET}\n\n" >&2
  printf "${DIM}  Atau tutup terminal ini lalu buka yang baru, ketik: octopus${RESET}\n" >&2
else
  printf "  Ketik ${BOLD}octopus${RESET} untuk mulai.\n" >&2
fi
printf "\n" >&2
