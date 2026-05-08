#!/usr/bin/env bash
set -euo pipefail

GITHUB_REPO="codinginid/ai-agent"
INSTALL_DIR="${OCTOPUS_INSTALL_DIR:-/usr/local/bin}"
BIN_NAME="octopus"

# ── Colors ────────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'
  GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
else
  BOLD=''; DIM=''; RESET=''; GREEN=''; CYAN=''; RED=''; YELLOW=''
fi

step()    { echo -e "${CYAN}${BOLD}  →${RESET} $1"; }
ok()      { echo -e "${GREEN}${BOLD}  ✓${RESET} $1"; }
warn()    { echo -e "${YELLOW}${BOLD}  !${RESET} $1"; }
die()     { echo -e "${RED}${BOLD}  ✗${RESET} $1"; echo; exit 1; }

# ── Spinner ───────────────────────────────────────────────────────────────────
_spin_pid=""

spinner_start() {
  local msg="$1"
  if [[ ! -t 1 ]]; then
    echo "  $msg"
    return
  fi
  (
    local frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    local i=0
    while true; do
      printf "\r${CYAN}  %s${RESET} ${DIM}%s${RESET}" "${frames[$((i % 10))]}" "$msg"
      sleep 0.08
      (( i++ )) || true
    done
  ) &
  _spin_pid=$!
}

spinner_stop() {
  if [[ -n "$_spin_pid" ]]; then
    kill "$_spin_pid" 2>/dev/null || true
    wait "$_spin_pid" 2>/dev/null || true
    _spin_pid=""
    printf "\r\033[2K"
  fi
}

trap 'spinner_stop' EXIT

# ── Banner ────────────────────────────────────────────────────────────────────
echo
echo -e "${CYAN}${BOLD}  ╭─────────────────────────────────╮${RESET}"
echo -e "${CYAN}${BOLD}  │   🐙  Octopus CLI Installer     │${RESET}"
echo -e "${CYAN}${BOLD}  ╰─────────────────────────────────╯${RESET}"
echo

# ── Resolve version ───────────────────────────────────────────────────────────
if [[ -n "${OCTOPUS_VERSION:-}" ]]; then
  VERSION="$OCTOPUS_VERSION"
else
  spinner_start "Fetching latest version..."
  API_RESPONSE=$(curl -fsSL "https://api.github.com/repos/${GITHUB_REPO}/releases/latest" 2>&1 || true)
  spinner_stop
  VERSION=$(echo "$API_RESPONSE" | grep '"tag_name"' | head -1 \
    | sed 's/.*"tag_name": *"\(.*\)".*/\1/' | sed 's/^v//')
  if [[ -z "$VERSION" ]]; then
    echo
    die "No release found at https://github.com/${GITHUB_REPO}/releases\n\n  Possible causes:\n    - No release has been published yet\n    - GitHub rate limit (retry: OCTOPUS_VERSION=x.y.z bash install.sh)"
  fi
  ok "Latest version: ${BOLD}v${VERSION}${RESET}"
fi

# ── Detect platform ───────────────────────────────────────────────────────────
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in
  x86_64)         ARCH="amd64" ;;
  aarch64|arm64)  ARCH="arm64" ;;
  *) die "Unsupported architecture: $ARCH" ;;
esac

if [[ "$OS" == "windows"* ]]; then
  BINARY_NAME="octopus-windows-amd64.exe"
else
  BINARY_NAME="octopus-${OS}-${ARCH}"
fi

step "Platform: ${OS}/${ARCH}"

DOWNLOAD_URL="https://github.com/${GITHUB_REPO}/releases/download/v${VERSION}/${BINARY_NAME}"

# ── Download ──────────────────────────────────────────────────────────────────
TMP=$(mktemp)
spinner_start "Downloading v${VERSION}..."
if ! curl -fsSL "$DOWNLOAD_URL" -o "$TMP" 2>/dev/null; then
  spinner_stop
  rm -f "$TMP"
  die "Download failed.\n  URL: $DOWNLOAD_URL\n  Check: https://github.com/${GITHUB_REPO}/releases"
fi
spinner_stop
chmod +x "$TMP"
ok "Downloaded"

# ── Install ───────────────────────────────────────────────────────────────────
spinner_start "Installing to ${INSTALL_DIR}..."
if [ -w "$INSTALL_DIR" ]; then
  mv "$TMP" "${INSTALL_DIR}/${BIN_NAME}"
else
  sudo mv "$TMP" "${INSTALL_DIR}/${BIN_NAME}"
fi
spinner_stop
ok "Installed → ${BOLD}${INSTALL_DIR}/${BIN_NAME}${RESET}"

# ── Verify ────────────────────────────────────────────────────────────────────
if command -v "$BIN_NAME" &>/dev/null || [[ -x "${INSTALL_DIR}/${BIN_NAME}" ]]; then
  INSTALLED_VER=$("${INSTALL_DIR}/${BIN_NAME}" --version 2>/dev/null | awk '{print $NF}' || echo "?")
  ok "Verified: octopus ${INSTALLED_VER}"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo
echo -e "${GREEN}${BOLD}  ╭─────────────────────────────────╮${RESET}"
echo -e "${GREEN}${BOLD}  │   ✓  Instalasi selesai!         │${RESET}"
echo -e "${GREEN}${BOLD}  ╰─────────────────────────────────╯${RESET}"
echo
echo -e "  Jalankan perintah berikut di terminal:"
echo
echo -e "  ${BOLD}  hash -r && octopus${RESET}"
echo
echo -e "  ${DIM}Atau buka terminal baru, lalu ketik: octopus${RESET}"
echo -e "  ${DIM}Ketik /login untuk mulai.${RESET}"
echo
