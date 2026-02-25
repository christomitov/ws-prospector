# Debugging

See also: [Docs Index](./README.md), [Architecture](./architecture.md), [Modules](./modules.md).

## Extension debug surface

`Wealthsimple Prospector` emits structured console logs prefixed with `[WSP]`.

It also exposes a page-level debug API on LinkedIn profile pages:

- `window.__WSP_DEBUG__.getSnapshot()`
- `window.__WSP_DEBUG__.getLogs()`
- `window.__WSP_DEBUG__.clearLogs()`

## CLI tailing via Chrome DevTools Protocol

Use `scripts/devtools-tail.mjs` to stream live logs from a LinkedIn tab.

1. Start Chrome with remote debugging enabled.
2. Load the unpacked extension (`dist/`).
3. Open a LinkedIn profile page.
4. Run:

```bash
pnpm debug:tail
```

Environment controls:

- `CHROME_DEBUG_HOST` (default `127.0.0.1`)
- `CHROME_DEBUG_PORT` (default `9222`)
- `DEBUG_TARGET_FILTER` (default `linkedin.com`)
- `WSP_ONLY=0` to show all console logs (default filters to `[WSP]`)

Example:

```bash
CHROME_DEBUG_PORT=9222 DEBUG_TARGET_FILTER=linkedin.com pnpm debug:tail
```

Notes:

- The tail script now serializes console object arguments, so background error payloads print as JSON fields instead of `[object Object]`.

## Fast local iteration (CRXJS-native)

You only need to load the unpacked extension once.

1. Start dev server: `pnpm dev`
2. Load `dist/` in `chrome://extensions` (Developer mode).
3. Keep `pnpm dev` running while editing.
4. Reload extension card if background/content-script updates are not reflected immediately.
5. Refresh the LinkedIn profile tab after extension reload.

Notes:

- You do **not** need to remove and add the extension again for each change.
- Content script updates require extension reload + page refresh on many Chrome builds.

### Full local quality gate

Run this before packaging or sharing a build:

```bash
pnpm gate
```

## Build a shareable zip

Use this when you want to hand the extension to someone for manual install in `chrome://extensions`.

```bash
pnpm bundle:zip
```

This command:

1. Builds the extension into `dist/`
2. Creates `wealthsimple-prospector.zip` at the repo root from `dist/`

## AI enrichment setup

- Use the drawer header settings cog to set provider (`ChatGPT` or `Gemini`), model, and key.
- Switching provider in the drawer auto-fills that provider's default model (`gpt-4.1-mini` or `gemini-2.5-flash`).
- Provider keys are stored in extension local storage (`chrome.storage.local`) as part of settings.
- You can also edit provider/model/keys in the options page.
- Enriched output is rendered in the drawer `AI Enrichment` section (signals and AI-generated score reasons).
- If AI enrich hangs or background messaging fails, drawer status surfaces an explicit error instead of indefinite loading.

## Message generation setup

- Drawer message generation uses one saved prompt from the `Edit Prompt` modal (no template selector in drawer).
- `Generate` and `Regenerate` send that prompt + full parsed profile context + AI signals/scores to background for provider-routed generation.
- Generated output is a single copy-ready message in one textarea.

## In-page drawer behavior

- The content script injects a fixed right-side drawer on LinkedIn profile pages.
- The drawer supports collapse/expand via a fixed top-right launcher and persists state in local storage.
- Drawer layout reserves bottom clearance (`--dc-bottom-clearance`) so the LinkedIn bottom messaging surface stays visible.

## Typecheck engine

- Type checking uses `tsgo` (`@typescript/native-preview`) via `pnpm typecheck`.
