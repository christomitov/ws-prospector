# Release Process

This is the manual release flow using `gh`.

## Prerequisites

1. Build artifacts exist from `./scripts/build_release.sh`.
2. You are authenticated with GitHub CLI (`gh auth status`).

## Manual Release (Tag + GitHub Release)

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

## Notes

1. Replace `v1.0.0` with the actual release version.
2. DMG is the main distribution artifact; ZIP can be kept as fallback.
