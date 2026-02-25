#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Load local overrides/secrets for signing/notarization.
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
fi

APP_SLUG="wealthsimple-prospector"
BIN_NAME="wealthsimple-prospector"
APP_DISPLAY_NAME="Wealthsimple Prospector"
APP_BUNDLE_NAME="${APP_DISPLAY_NAME}.app"
APP_BUNDLE_PATH="dist/${APP_BUNDLE_NAME}"
APP_CONTENTS_DIR="${APP_BUNDLE_PATH}/Contents"
APP_MACOS_DIR="${APP_CONTENTS_DIR}/MacOS"
APP_RESOURCES_DIR="${APP_CONTENTS_DIR}/Resources"
APP_FRAMEWORKS_DIR="${APP_CONTENTS_DIR}/Frameworks"
APP_PAYLOAD_DIR="${APP_RESOURCES_DIR}/app"
APP_LAUNCHER_NAME="wealthsimple-prospector-launcher"
APP_LAUNCHER_PATH="${APP_MACOS_DIR}/${APP_LAUNCHER_NAME}"
APP_BUNDLE_ID="${APPLE_BUNDLE_ID:-com.christo.wealthsimpleprospector}"
LAUNCHER_SOURCE="scripts/macos_launcher.swift"
NODE_ENTITLEMENTS_FILE="scripts/node_hardened_runtime.entitlements"
ENTRY_FILE="scripts/pyinstaller_entry.py"
ZIP_PATH="dist/${APP_SLUG}-macos.zip"
DMG_PATH="dist/${APP_SLUG}-macos.dmg"
DIST_APP_DIR="dist/${BIN_NAME}"
SIGN_IDENTITY="${APPLE_SIGN_IDENTITY:-}"
NOTARY_PROFILE="${APPLE_NOTARY_PROFILE:-ws-notary}"
APPLE_ID_VALUE="${APPLE_ID:-}"
APPLE_TEAM_ID_VALUE="${APPLE_TEAM_ID:-2H56V7T355}"
APPLE_APP_PASSWORD_VALUE="${APPLE_APP_PASSWORD:-}"
SKIP_NOTARIZATION="${WSP_SKIP_NOTARIZATION:-0}"
SPARKLE_ENABLED="${WSP_ENABLE_SPARKLE:-1}"
SPARKLE_VERSION="${WSP_SPARKLE_VERSION:-2.9.0}"
SPARKLE_FEED_URL="${WSP_SPARKLE_FEED_URL:-https://christomitov.github.io/ws-prospector/appcast.xml}"
SPARKLE_PUBLIC_KEY="${WSP_SPARKLE_PUBLIC_KEY:-}"
SPARKLE_FRAMEWORK_SOURCE="${WSP_SPARKLE_FRAMEWORK_SOURCE:-}"
SPARKLE_CACHE_DIR="${ROOT_DIR}/.build/sparkle"
DMG_CREATED=0

if [[ "$SPARKLE_ENABLED" == "1" && -z "$SPARKLE_PUBLIC_KEY" ]]; then
  echo "==> Warning: WSP_SPARKLE_PUBLIC_KEY is empty. Sparkle will be embedded, but update checks are disabled until key is set."
fi

codesign_retry() {
  local attempts=0
  local max_attempts=3
  while true; do
    if codesign "$@"; then
      return 0
    fi
    attempts=$((attempts + 1))
    if [[ "$attempts" -ge "$max_attempts" ]]; then
      return 1
    fi
    sleep 1
  done
}

download_sparkle_framework() {
  if [[ "$SPARKLE_ENABLED" != "1" ]]; then
    return
  fi

  mkdir -p "$APP_FRAMEWORKS_DIR" "$SPARKLE_CACHE_DIR"

  local framework_source="$SPARKLE_FRAMEWORK_SOURCE"
  if [[ -z "$framework_source" ]]; then
    local archive_name="Sparkle-${SPARKLE_VERSION}.tar.xz"
    local archive_path="${SPARKLE_CACHE_DIR}/${archive_name}"
    local extract_dir="${SPARKLE_CACHE_DIR}/Sparkle-${SPARKLE_VERSION}"
    local download_url="https://github.com/sparkle-project/Sparkle/releases/download/${SPARKLE_VERSION}/${archive_name}"

    if [[ ! -f "$archive_path" ]]; then
      echo "==> Downloading Sparkle ${SPARKLE_VERSION}..."
      curl -fsSL "$download_url" -o "$archive_path"
    fi

    rm -rf "$extract_dir"
    mkdir -p "$extract_dir"
    tar -xJf "$archive_path" -C "$extract_dir"

    framework_source="$(find "$extract_dir" -type d -path "*/Sparkle.xcframework/macos-arm64_x86_64/Sparkle.framework" -print -quit)"
    if [[ -z "$framework_source" ]]; then
      framework_source="$(find "$extract_dir" -type d -path "*/Sparkle.xcframework/macos-*/Sparkle.framework" -print -quit)"
    fi
    if [[ -z "$framework_source" ]]; then
      framework_source="$(find "$extract_dir" -type d -name "Sparkle.framework" -print -quit)"
    fi
  fi

  if [[ -z "$framework_source" || ! -d "$framework_source" ]]; then
    echo "Error: Sparkle.framework not found (set WSP_SPARKLE_FRAMEWORK_SOURCE to override)." >&2
    exit 1
  fi

  echo "==> Embedding Sparkle.framework..."
  rm -rf "${APP_FRAMEWORKS_DIR}/Sparkle.framework"
  cp -R "$framework_source" "${APP_FRAMEWORKS_DIR}/Sparkle.framework"
}

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

echo "==> Creating .app bundle..."
rm -rf "${APP_BUNDLE_PATH}"
mkdir -p "${APP_MACOS_DIR}" "${APP_PAYLOAD_DIR}" "${APP_FRAMEWORKS_DIR}"

SPARKLE_PLIST_KEYS=""
if [[ "$SPARKLE_ENABLED" == "1" ]]; then
  SPARKLE_PLIST_KEYS+=$'  <key>SUEnableAutomaticChecks</key>\n  <true/>\n'
  SPARKLE_PLIST_KEYS+=$'  <key>SUScheduledCheckInterval</key>\n  <integer>86400</integer>\n'
  if [[ -n "$SPARKLE_FEED_URL" ]]; then
    SPARKLE_PLIST_KEYS+=$'  <key>SUFeedURL</key>\n'
    SPARKLE_PLIST_KEYS+="  <string>${SPARKLE_FEED_URL}</string>"$'\n'
  fi
  if [[ -n "$SPARKLE_PUBLIC_KEY" ]]; then
    SPARKLE_PLIST_KEYS+=$'  <key>SUPublicEDKey</key>\n'
    SPARKLE_PLIST_KEYS+="  <string>${SPARKLE_PUBLIC_KEY}</string>"$'\n'
  fi
fi

cat > "${APP_CONTENTS_DIR}/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleDisplayName</key>
  <string>${APP_DISPLAY_NAME}</string>
  <key>CFBundleExecutable</key>
  <string>${APP_LAUNCHER_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>${APP_BUNDLE_ID}</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>${APP_DISPLAY_NAME}</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
${SPARKLE_PLIST_KEYS}
</dict>
</plist>
EOF

cp -R "${DIST_APP_DIR}/." "${APP_PAYLOAD_DIR}/"
download_sparkle_framework

if command -v xcrun >/dev/null 2>&1 && xcrun --find swiftc >/dev/null 2>&1; then
  echo "==> Compiling native macOS launcher..."
  if [[ "$SPARKLE_ENABLED" == "1" ]]; then
    xcrun swiftc -O -framework Cocoa -F "${APP_FRAMEWORKS_DIR}" -framework Sparkle "${LAUNCHER_SOURCE}" -o "${APP_LAUNCHER_PATH}"
  else
    xcrun swiftc -O -framework Cocoa "${LAUNCHER_SOURCE}" -o "${APP_LAUNCHER_PATH}"
  fi
else
  echo "==> swiftc not found; falling back to shell launcher."
  cat > "${APP_LAUNCHER_PATH}" <<'SH'
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTENTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PAYLOAD_DIR="$CONTENTS_DIR/Resources/app"
exec "$PAYLOAD_DIR/wealthsimple-prospector"
SH
fi
chmod +x "${APP_LAUNCHER_PATH}"

if [[ -z "$SIGN_IDENTITY" ]]; then
  SIGN_IDENTITY="$(
    security find-identity -v -p codesigning \
      | sed -n 's/.*"\(Developer ID Application:.*\)"/\1/p' \
      | head -n1
  )"
fi

if [[ -n "$SIGN_IDENTITY" ]]; then
  echo "==> Code signing with identity: ${SIGN_IDENTITY}"
  while IFS= read -r -d '' f; do
    if [[ "$f" == "${APP_LAUNCHER_PATH}" ]]; then
      continue
    fi

    file_info="$(file -b "$f" || true)"
    if [[ "$file_info" != *"Mach-O"* ]]; then
      continue
    fi

    sign_args=(--force --timestamp --sign "$SIGN_IDENTITY")
    if [[ "$file_info" == *"executable"* ]]; then
      sign_args+=(--options runtime)
      if [[ "$f" == *"/patchright/driver/node" ]]; then
        sign_args+=(--entitlements "$NODE_ENTITLEMENTS_FILE")
      fi
    fi
    codesign_retry "${sign_args[@]}" "$f"
  done < <(find "$APP_BUNDLE_PATH" -type f -print0)

  codesign_retry --force --timestamp --options runtime --sign "$SIGN_IDENTITY" "${APP_BUNDLE_PATH}"
  codesign --verify --deep --strict --verbose=2 "${APP_BUNDLE_PATH}"
else
  echo "==> No Developer ID Application identity found; skipping code signing."
fi

echo "==> Creating zip archive..."
rm -f "$ZIP_PATH"
ditto -c -k --sequesterRsrc --keepParent "${APP_BUNDLE_PATH}" "$ZIP_PATH"

if [[ "$SKIP_NOTARIZATION" == "1" ]]; then
  HAVE_NOTARY_PROFILE=0
elif xcrun notarytool history --keychain-profile "$NOTARY_PROFILE" >/dev/null 2>&1; then
  HAVE_NOTARY_PROFILE=1
else
  HAVE_NOTARY_PROFILE=0
fi

if [[ "$SKIP_NOTARIZATION" != "1" ]] && [[ "$HAVE_NOTARY_PROFILE" -eq 0 ]] && [[ -n "$APPLE_ID_VALUE" ]] && [[ -n "$APPLE_APP_PASSWORD_VALUE" ]]; then
  echo "==> Creating notarytool profile '${NOTARY_PROFILE}' from environment..."
  xcrun notarytool store-credentials "$NOTARY_PROFILE" \
    --apple-id "$APPLE_ID_VALUE" \
    --team-id "$APPLE_TEAM_ID_VALUE" \
    --password "$APPLE_APP_PASSWORD_VALUE"
fi

if [[ "$HAVE_NOTARY_PROFILE" -eq 1 ]]; then
  echo "==> Creating DMG for notarization..."
  DMG_STAGING_DIR="$(mktemp -d)"
  cp -R "${APP_BUNDLE_PATH}" "${DMG_STAGING_DIR}/${APP_BUNDLE_NAME}"
  ln -s /Applications "${DMG_STAGING_DIR}/Applications"
  rm -f "$DMG_PATH"
  hdiutil create \
    -volname "${APP_DISPLAY_NAME}" \
    -srcfolder "$DMG_STAGING_DIR" \
    -ov \
    -format UDZO \
    "$DMG_PATH" >/dev/null
  DMG_CREATED=1
  rm -rf "$DMG_STAGING_DIR"

  echo "==> Submitting DMG for notarization (profile: ${NOTARY_PROFILE})..."
  xcrun notarytool submit "$DMG_PATH" --keychain-profile "$NOTARY_PROFILE" --wait

  echo "==> Stapling notarization ticket..."
  xcrun stapler staple "$DMG_PATH"
  xcrun stapler validate "$DMG_PATH" || true
else
  if [[ "$SKIP_NOTARIZATION" == "1" ]]; then
    echo "==> Skipping notarization (WSP_SKIP_NOTARIZATION=1)."
  else
    echo "==> Skipping notarization: no notary profile '${NOTARY_PROFILE}' found."
    echo "   One-time setup:"
    echo "   1) Fill APPLE_ID / APPLE_APP_PASSWORD in .env and rerun this script, OR"
    echo "   2) Run:"
    echo "      xcrun notarytool store-credentials \"${NOTARY_PROFILE}\" --apple-id \"<apple-id>\" --team-id \"${APPLE_TEAM_ID_VALUE}\""
  fi
fi

echo "Build complete:"
echo "  App bundle: ${APP_BUNDLE_PATH}"
echo "  Runtime payload: ${DIST_APP_DIR}"
echo "  Release zip: ${ZIP_PATH}"
if [[ "$DMG_CREATED" -eq 1 ]]; then
  echo "  Notarized DMG: ${DMG_PATH}"
fi
