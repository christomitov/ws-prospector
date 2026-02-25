# Wealthsimple Prospector Extension

Chrome extension for LinkedIn profile prospecting with:

- profile parsing (`/in/*`)
- AI enrichment (OpenAI or Gemini)
- AI outreach message generation
- in-page right-side drawer workflow with launcher and collapse/expand state

This repo uses Vite + CRXJS + TypeScript + React.

## Prerequisites

- Node.js 20+
- pnpm 10+
- Chrome (Developer mode enabled for unpacked extension)

## Install

```bash
pnpm install
```

## Build and load extension

```bash
pnpm build
```

Then:

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select the `dist/` folder

## Local development loop (CRXJS-native)

```bash
pnpm dev
```

Then:

1. Open `chrome://extensions`
2. Load `dist/` as unpacked (as shown by CRXJS startup output)
3. Keep `pnpm dev` running while you edit

Notes:

- CRXJS watches and rebuilds extension assets continuously during `pnpm dev`.
- Reload the extension card if background/content-script changes are not picked up immediately on your Chrome build.
- Refresh the LinkedIn tab after reloading the extension for content script updates.

## Quality gate

```bash
pnpm gate
```

Runs:

- format check (`oxfmt`)
- lint (`oxlint`)
- typecheck (`tsgo`)
- tests (`vitest`)
- production build (`vite`)

## Tests

```bash
pnpm test
```

Current coverage focus:

- LinkedIn parsing logic
- scoring logic

## Remote debug tail (Chrome DevTools Protocol)

Start Chrome with remote debugging (typically port `9222`), open a LinkedIn profile page, then run:

```bash
pnpm debug:tail
```

Useful env vars:

- `CHROME_DEBUG_HOST` (default `127.0.0.1`)
- `CHROME_DEBUG_PORT` (default `9222`)
- `DEBUG_TARGET_FILTER` (default `linkedin.com`)
- `WSP_ONLY=0` to show all logs (default shows `[WSP]` logs only)

Example:

```bash
CHROME_DEBUG_PORT=9222 DEBUG_TARGET_FILTER=linkedin.com pnpm debug:tail
```

## Bundle for sharing

```bash
pnpm bundle:zip
```

Creates `wealthsimple-prospector.zip` at repo root from the latest `dist/` build.

## Project docs

Detailed architecture and module contracts are in:

- `docs/README.md`
- `docs/architecture.md`
- `docs/modules.md`
- `docs/data-model.md`
- `docs/debugging.md`
- `docs/roadmap.md`
