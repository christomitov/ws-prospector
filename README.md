# Wealthsimple Prospector Monorepo

This repository contains two related products:

1. `src/linkedin_leads` — Python app (local web UI + API + scraping/connector CLI).
2. `apps/extension` — browser extension app.

The goal is to keep lead collection workflows, extension work, and shared docs in one place while keeping each app isolated.

## What The Python App Does

1. LinkedIn people search extraction.
2. Sales Navigator extraction (including pasted Sales Nav URLs).
3. Company people extraction.
4. Lead storage/export (SQLite + CSV/JSON).
5. Queue-based auto connector.
6. CLI collection flow for agent-driven enrichment (`collect` command).

## Repo Layout

- `src/linkedin_leads/` — Python application source.
- `apps/extension/` — extension source, docs, and build config.
- `docs/` — Python app docs (API, architecture, release process).
- `skills/` — agent skills (including collector skill instructions).

## Quick Start (Python App)

```bash
uv sync
uv run ws-prospector
```

Open: `http://127.0.0.1:8000`

## CLI (Agent-Friendly)

Run from repo root with `uv run` (no global PATH dependency):

```bash
uv run ws-prospector-debug status
uv run ws-prospector-debug collect --query "founder" --source sales_navigator --max-pages 3
uv run ws-prospector-debug collect --sales-url "https://www.linkedin.com/sales/search/people?..." --json-out out/leads.json --csv-out out/leads.csv
```

`collect` outputs:

1. Structured JSON for downstream LLM qualification.
2. Flattened CSV for Google Sheets/manual sharing.

## Extension Workflows

From repo root:

```bash
pnpm ext:dev
pnpm ext:build
pnpm ext:test
pnpm ext:lint
```

Or run commands directly inside `apps/extension`.

## Documentation

Start here:

- [Documentation Index](docs/README.md)
- [API Reference](docs/API.md)
- [Architecture](docs/architecture.md)
- [Release Process](docs/release-process.md)

Extension-specific docs:

- [Extension Docs](apps/extension/docs/README.md)

## Release Notes

The root README intentionally stays focused on development usage.
For macOS packaging, signing, notarization, and Sparkle updater details, use:

- [Release Process](docs/release-process.md)
