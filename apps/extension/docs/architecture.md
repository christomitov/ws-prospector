# Architecture

See also: [Docs Index](./README.md), [Modules](./modules.md), [Data Model](./data-model.md), [Debugging](./debugging.md), [Roadmap](./roadmap.md).

## Product surface

`Wealthsimple Prospector` is a Chrome extension (Manifest V3) with:

- Content script in-page drawer on LinkedIn profile pages (`/in/*`)
- Background service worker for extension lifecycle and future network delegation
- Options page for settings/rule editing
- Popup for quick status and settings access

## Runtime boundaries

- `Content script`: in-page right drawer UI + LinkedIn DOM parsing + launcher/collapse behavior.
- `Background`: lifecycle + structured debug log buffer and retrieval channel.
- `Background`: provider-routed enrichment + outreach-generation calls (OpenAI Responses API or Gemini GenerateContent API) using locally stored keys.
- `Options`: editable prompts/rules + AI settings (`enabled`, `provider`, `model`, provider keys).
- `Storage`: `chrome.storage.local` wrapper for settings/prospect/event persistence.

## Non-goals for this phase

- CRM integrations (explicitly deferred)
- Automated LinkedIn actions
- Bulk scraping and background crawling
