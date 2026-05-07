#!/usr/bin/env bash
set -euo pipefail

VERSION="0.2.0"
GITHUB_REPO="codinginid/octopus"
INSTALL_DIR="/usr/local/bin"
BIN_NAME="octopus"

# Detect OS and arch
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in
  x86_64) ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *) echo "Unsupported arch: $ARCH"; exit 1 ;;
esac

BINARY_NAME="octopus-${OS}-${ARCH}"
DOWNLOAD_URL="https://github.com/${GITHUB_REPO}/releases/download/v${VERSION}/${BINARY_NAME}"

echo "Installing Octopus CLI v${VERSION}..."
echo "Platform: ${OS}/${ARCH}"

# Download
TMP=$(mktemp)
curl -fsSL "$DOWNLOAD_URL" -o "$TMP"
chmod +x "$TMP"

# Install
if [ -w "$INSTALL_DIR" ]; then
  mv "$TMP" "${INSTALL_DIR}/${BIN_NAME}"
else
  sudo mv "$TMP" "${INSTALL_DIR}/${BIN_NAME}"
fi

echo ""
echo "✓ Octopus CLI installed to ${INSTALL_DIR}/${BIN_NAME}"
echo ""
echo "Run: octopus"
echo "Then type /login to get started."
