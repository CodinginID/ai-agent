#!/usr/bin/env bash
set -euo pipefail

GITHUB_REPO="codinginid/ai-agent"
INSTALL_DIR="${OCTOPUS_INSTALL_DIR:-/usr/local/bin}"
BIN_NAME="octopus"

# ── Resolve version ──────────────────────────────────────────────────────────
# If OCTOPUS_VERSION is set use it; otherwise fetch latest from GitHub API.
if [[ -n "${OCTOPUS_VERSION:-}" ]]; then
  VERSION="$OCTOPUS_VERSION"
else
  echo "Fetching latest version..."
  VERSION=$(curl -fsSL "https://api.github.com/repos/${GITHUB_REPO}/releases/latest" \
    | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"\(.*\)".*/\1/' | sed 's/^v//')
  if [[ -z "$VERSION" ]]; then
    echo "ERROR: could not detect latest version. Set OCTOPUS_VERSION and retry."
    exit 1
  fi
fi

# ── Detect platform ──────────────────────────────────────────────────────────
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in
  x86_64)          ARCH="amd64" ;;
  aarch64|arm64)   ARCH="arm64" ;;
  *) echo "Unsupported arch: $ARCH"; exit 1 ;;
esac

if [[ "$OS" == "windows"* ]]; then
  BINARY_NAME="octopus-windows-amd64.exe"
else
  BINARY_NAME="octopus-${OS}-${ARCH}"
fi

DOWNLOAD_URL="https://github.com/${GITHUB_REPO}/releases/download/v${VERSION}/${BINARY_NAME}"

echo "Installing Octopus CLI v${VERSION} (${OS}/${ARCH})..."

# ── Download ─────────────────────────────────────────────────────────────────
TMP=$(mktemp)
if ! curl -fsSL "$DOWNLOAD_URL" -o "$TMP"; then
  echo "ERROR: download failed from $DOWNLOAD_URL"
  echo "  Check: https://github.com/${GITHUB_REPO}/releases"
  rm -f "$TMP"
  exit 1
fi
chmod +x "$TMP"

# ── Install ──────────────────────────────────────────────────────────────────
if [ -w "$INSTALL_DIR" ]; then
  mv "$TMP" "${INSTALL_DIR}/${BIN_NAME}"
else
  echo "Installing to ${INSTALL_DIR} (requires sudo)..."
  sudo mv "$TMP" "${INSTALL_DIR}/${BIN_NAME}"
fi

echo ""
echo "✓ Octopus CLI v${VERSION} installed → ${INSTALL_DIR}/${BIN_NAME}"
echo ""
echo "  Jalankan: octopus"
echo "  Lalu ketik /login untuk mulai."
echo ""
