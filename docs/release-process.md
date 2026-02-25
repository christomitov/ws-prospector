# Release Process

This is the manual release flow using `gh` + Sparkle.

## Prerequisites

1. Build artifacts exist from `./scripts/build_release.sh`.
2. You are authenticated with GitHub CLI (`gh auth status`).
3. GitHub Pages is enabled for the repo (either `main` `/` or `gh-pages` `/`).
4. `WSP_SPARKLE_PUBLIC_KEY` is set in `.env`.

## GitHub Pages Source

Either source works:

1. `main` branch + `/` path (simplest, already supported here).
2. `gh-pages` branch + `/` path (clean separation).

For this repo, `main` + `/` is fine and serves:

`https://christomitov.github.io/ws-prospector/appcast.xml`

## Sparkle Key Setup (One Time)

1. Build once (this downloads Sparkle tools into `.build/sparkle/`):

```bash
./scripts/build_release.sh
```

2. Generate Sparkle signing keys:

```bash
./.build/sparkle/Sparkle-2.9.0/bin/generate_keys
```

3. Copy the printed `SUPublicEDKey` value into `.env`:

```bash
WSP_SPARKLE_PUBLIC_KEY=<paste-public-key>
```

## Manual Release (Tag + GitHub Release + Appcast)

1. Build notarized artifacts locally:

```bash
./scripts/build_release.sh
```

2. Create and push a version tag:

```bash
git tag -a v1.0.0 -m "v1.0.0"
git push origin v1.0.0
```

3. Create a GitHub release and upload assets:

```bash
gh release create v1.0.0 \
  dist/wealthsimple-prospector-macos.dmg \
  dist/wealthsimple-prospector-macos.zip \
  --title "v1.0.0" \
  --notes "Release notes here"
```

4. Generate/update `appcast.xml` using the release asset URL prefix:

```bash
mkdir -p .release-feed
cp dist/wealthsimple-prospector-macos.dmg .release-feed/

./.build/sparkle/Sparkle-2.9.0/bin/generate_appcast \
  --account ed25519 \
  --download-url-prefix "https://github.com/christomitov/ws-prospector/releases/download/v1.0.0" \
  .release-feed

cp .release-feed/appcast.xml appcast.xml
```

5. Commit and push the updated appcast:

```bash
git add appcast.xml
git commit -m "Update appcast for v1.0.0"
git push origin main
```

## Notes

1. Replace `v1.0.0` with the actual release version.
2. DMG is the main distribution artifact; ZIP can be kept as fallback.
3. Keep `.release-feed/` around locally if you want multi-version appcast history.
