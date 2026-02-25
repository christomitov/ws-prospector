# Wealthsimple Prospector Monorepo

Wealthsimple Prospector is a multi-surface lead intelligence platform (extension, CLI, and web app) for discovering, enriching, and curating high-quality LinkedIn and Sales Navigator prospects for outbound.

## Product Surfaces

1. Web app + API (`src/linkedin_leads`) for search, review, queueing, and operations.
2. CLI (`ws-prospector-debug` / `ws-prospector-cli`) for agent-driven collection and enrichment runs.
3. Browser extension (`apps/extension`) for in-browser workflows.

## Core Workflow

1. Find prospects from LinkedIn search, Sales Navigator URL, or company pages.
2. Enrich profiles (about, experience, education, activity) into structured records.
3. Curate and qualify leads for prospecting with JSON/CSV outputs.
4. Share CSV in Sheets and optionally run connection queue workflows.

## Repository Layout

- `src/linkedin_leads/` — Python app source (web UI, API, spiders, storage, connector).
- `apps/extension/` — extension source, docs, and build config.
- `docs/` — Python app docs (API, architecture, release process).
- `skills/` — agent skill instructions (including collector workflow guidance).

## Run The Web App

```bash
uv sync
uv run ws-prospector
```

Open: `http://127.0.0.1:8000`

## Run The CLI

Run from repo root with `uv run` (no global PATH dependency):

```bash
uv run ws-prospector-debug status
uv run ws-prospector-debug collect --query "founder" --source sales_navigator --max-pages 3
uv run ws-prospector-debug collect --sales-url "https://www.linkedin.com/sales/search/people?..." --json-out out/leads.json --csv-out out/leads.csv
```

`collect` outputs:

1. Structured JSON for downstream LLM evaluation.
2. Flattened CSV for Sheets/manual sharing.

## Run The Extension

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
- [Extension Docs](apps/extension/docs/README.md)

## Release Notes

The root README stays focused on product purpose and development usage.
For macOS packaging/signing/notarization/Sparkle details, use:

- [Release Process](docs/release-process.md)
