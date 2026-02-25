# Modules

See also: [Architecture](./architecture.md), [Data Model](./data-model.md), [Debugging](./debugging.md), [Roadmap](./roadmap.md).

## `src/content/main.ts`

Responsibilities:

- Inject and manage the in-page right drawer (`#dc-root`) on LinkedIn profile pages.
- Persist and restore collapsed state via storage key `deal_copilot:ui_collapsed`.
- Parse LinkedIn profile content locally with retry logic for dynamic rendering.
- Trigger provider-routed AI enrichment and message generation through background messaging.
- Expose page debug surface via `window.__WSP_DEBUG__`.

## `src/content/sidebar.css`

Responsibilities:

- Style the in-page drawer and launcher UI.
- Keep drawer fixed to the right with bottom clearance so LinkedIn bottom messaging UI remains visible.

## `src/lib/parsing.ts`

Responsibilities:

- Identify valid LinkedIn profile URLs.
- Normalize profile URLs for stable storage keys.
- Extract visible profile fields with fallback selectors and top-card text heuristics.
- Extract section-level context from `About`, `Experience`, and `Activity`.

## `src/lib/scoring.ts`

Responsibilities:

- Apply weighted rule sets to profile data.
- Return clamped scores and explainable reasons.
- Derive heuristic high-level signals from parsed profile context.

## `src/lib/storage.ts`

Responsibilities:

- Centralize `chrome.storage.local` operations.
- Provide defaults and typed read/write helpers.

## `src/options/*`

Responsibilities:

- Edit the single outreach prompt used by in-page drawer generation (via settings).
- Edit prompt templates and default prompt selection.
- Edit ICP/capacity rule JSON.
- Persist privacy toggles.
- Persist AI settings (enabled, provider, model, provider keys).

## `src/background/index.ts`

Responsibilities:

- Extension lifecycle hooks.
- Structured debug log ingestion and retrieval.
- Execute provider-routed enrichment calls (OpenAI or Gemini) and return parsed JSON payloads to content script.
- Execute provider-routed outreach generation using the saved single outreach prompt + full profile context.
