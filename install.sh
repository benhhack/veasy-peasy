#!/bin/bash
set -euo pipefail

REPO="benhhack/veasy-peasy"
BIN_NAME="vzpz"

RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m'

err() { echo -e "${RED}error:${NC} $1" >&2; exit 1; }

# --- OS check ----------------------------------------------------------------
[ "$(uname -s)" = "Darwin" ] || err "this installer only supports macOS"

# --- Architecture -------------------------------------------------------------
case "$(uname -m)" in
  arm64|aarch64) ASSET="vzpz-aarch64-darwin" ;;
  x86_64)        ASSET="vzpz-x86_64-darwin"  ;;
  *)             err "unsupported architecture: $(uname -m)" ;;
esac

# --- Latest release -----------------------------------------------------------
echo "fetching latest release..."
TAG=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
  | grep '"tag_name"' | head -1 | cut -d'"' -f4) \
  || err "could not determine latest release"

URL="https://github.com/${REPO}/releases/download/${TAG}/${ASSET}"

# --- Download -----------------------------------------------------------------
INSTALL_DIR="${INSTALL_DIR:-${HOME}/.local/bin}"
mkdir -p "${INSTALL_DIR}"

echo "downloading ${BIN_NAME} ${TAG} (${ASSET})..."
curl -fSL --progress-bar -o "${INSTALL_DIR}/${BIN_NAME}" "${URL}" \
  || err "download failed — check ${URL}"

chmod +x "${INSTALL_DIR}/${BIN_NAME}"

# --- PATH hint ----------------------------------------------------------------
if [[ ":${PATH}:" != *":${INSTALL_DIR}:"* ]]; then
  echo ""
  echo -e "${BOLD}add to your shell profile:${NC}"
  echo "  export PATH=\"\${HOME}/.local/bin:\${PATH}\""
  echo ""
fi

echo -e "${GREEN}${BIN_NAME} ${TAG} installed to ${INSTALL_DIR}/${BIN_NAME}${NC}"
"${INSTALL_DIR}/${BIN_NAME}" --version
