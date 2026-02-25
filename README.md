# Wealthsimple Prospector

Wealthsimple Prospector is a local lead discovery app with a web UI and API.

Supported functionality:

1. LinkedIn people search extraction.
2. Sales Navigator extraction (including pasted Sales Nav URLs).
3. Company people extraction.
4. Lead storage/export.
5. Queue-based auto connector.

## Run Locally

```bash
uv sync
uv run ws-prospector
```

Open `http://127.0.0.1:8000`.

Debug CLI:

```bash
uv run ws-prospector-debug status
uv run ws-prospector-debug html 1
uv run ws-prospector-debug parse 1
```

## Build Release (Signed Zip + Optional Notarized DMG)

Build a shareable macOS zip your friend can run without installing Python/uv:

```bash
./scripts/build_release.sh
```

Output:

- `dist/Wealthsimple Prospector.app`
- `dist/wealthsimple-prospector-macos.zip`
- `dist/wealthsimple-prospector-macos.dmg` (only when notarization is configured)

Notarization setup (one time, easiest path):

1. Copy `.env.example` to `.env`.
2. Fill `APPLE_ID` + `APPLE_APP_PASSWORD` (Apple app-specific password).
3. Run `./scripts/build_release.sh`.

The script will auto-create the `ws-notary` keychain profile if missing.

Manual setup alternative:

```bash
xcrun notarytool store-credentials "ws-notary" \
  --apple-id "<your-apple-id>" \
  --team-id "2H56V7T355"
```

Then run the same build command. The script will:

1. Build PyInstaller output.
2. Wrap it in a native `.app` bundle.
3. Sign binaries with your `Developer ID Application` cert.
4. Create the zip.
5. Create, submit, and staple a DMG notarization ticket (if `ws-notary` exists).

Optional overrides:

- `APPLE_SIGN_IDENTITY`: explicit signing identity.
- `APPLE_NOTARY_PROFILE`: custom notarytool keychain profile name.
- `WSP_MACOS_DEPLOYMENT_TARGET`: minimum macOS version for the app binaries (default: `11.0`).
- `WSP_ENABLE_SPARKLE`: set `1` (default) to embed Sparkle updater.
- `WSP_SPARKLE_FEED_URL`: appcast URL (default: project GitHub Pages appcast).
- `WSP_SPARKLE_PUBLIC_KEY`: Sparkle `SUPublicEDKey` value.

Friend flow:

1. Open the `.dmg`.
2. Drag `Wealthsimple Prospector.app` to Applications.
3. Launch `Wealthsimple Prospector.app`.

Notes:

1. Chrome must be installed on the target machine.
2. Build on the same architecture as the target machine (Apple Silicon vs Intel).
3. Use a low `WSP_MACOS_DEPLOYMENT_TARGET` (default `11.0`) for broad macOS support.

## Docs

Start here:

- [Documentation Index](docs/README.md)
- [Release Process](docs/release-process.md)

## Auto Updates (Sparkle)

The native launcher embeds Sparkle when `WSP_ENABLE_SPARKLE=1`.
To enable actual update checks, set `WSP_SPARKLE_PUBLIC_KEY` in `.env` and keep
`appcast.xml` published on GitHub Pages.
