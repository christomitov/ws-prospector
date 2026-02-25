# Setup And Run

See also: [Architecture](./architecture.md), [API Reference](./API.md)

## Requirements

1. Python 3.10+
2. `uv` for dependency management and running scripts
3. Chrome installed locally (used by patchright/scrapling flows)

## Install

```bash
uv sync
```

## Run Server + UI

```bash
uv run ws-prospector
```

Open:

`http://127.0.0.1:8000`

## Login Flow

1. Click `Connect LinkedIn` in the UI.
2. Complete LinkedIn login in the opened browser.
3. Session is stored in a persistent profile and reused for scraping/connecting.

## Useful Commands

```bash
uv run ws-prospector-debug status
uv run ws-prospector-debug html 1
uv run ws-prospector-debug parse 1
uv run ws-prospector-debug collect --query "founder" --source sales_navigator --max-pages 3
```
