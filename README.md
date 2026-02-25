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

## Build Release Zip (PyInstaller)

Build a shareable macOS zip your friend can run without installing Python/uv:

```bash
./scripts/build_release.sh
```

Output:

- `dist/wealthsimple-prospector-macos.zip`

Friend flow:

1. Unzip.
2. Double-click `start.command`.
3. Open `http://127.0.0.1:8000`.

Notes:

1. Chrome must be installed on the target machine.
2. Build on the same OS/architecture as the target machine.

## Docs

Start here:

- [Documentation Index](docs/README.md)
