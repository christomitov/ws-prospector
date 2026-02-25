#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_SLUG="wealthsimple-prospector"
BIN_NAME="wealthsimple-prospector"
ENTRY_FILE="scripts/pyinstaller_entry.py"
ZIP_PATH="dist/${APP_SLUG}-macos.zip"
DIST_APP_DIR="dist/${BIN_NAME}"

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: uv is required to build the release bundle." >&2
  echo "Install uv: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

echo "==> Syncing dependencies (including dev tools)..."
uv sync --group dev

echo "==> Building PyInstaller app bundle..."
uv run pyinstaller "$ENTRY_FILE" \
  --name "$BIN_NAME" \
  --onedir \
  --clean \
  --noconfirm \
  --collect-all scrapling \
  --collect-all patchright \
  --collect-all browserforge \
  --collect-all apify_fingerprint_datapoints \
  --collect-all tld \
  --add-data "src/linkedin_leads/frontend:linkedin_leads/frontend"

echo "==> Creating launcher script..."
cat > "${DIST_APP_DIR}/start.command" <<'SH'
#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/wealthsimple-prospector"
SH
chmod +x "${DIST_APP_DIR}/start.command"

echo "==> Creating zip archive..."
rm -f "$ZIP_PATH"
(cd dist && zip -r "$(basename "$ZIP_PATH")" "$BIN_NAME" >/dev/null)

echo "Build complete:"
echo "  App folder: ${DIST_APP_DIR}"
echo "  Release zip: ${ZIP_PATH}"
