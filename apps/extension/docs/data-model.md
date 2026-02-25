# Data Model

See also: [Architecture](./architecture.md), [Modules](./modules.md), [Debugging](./debugging.md), [Roadmap](./roadmap.md).

## Primary types

Defined in `src/lib/types.ts`:

- `UserSettings`
- `PromptTemplate`
- `RuleDefinition`
- `ProspectSnapshot`
- `ScoreBreakdown`
- `GeneratedMessages`
- `ProspectRecord`
- `ActivityEvent`
- `DebugEntry`

Notable current fields:

- `UserSettings.llmEnabled`, `UserSettings.llmProvider`, `UserSettings.llmModel`
- `UserSettings.openAiApiKey`, `UserSettings.geminiApiKey`
- `UserSettings.outreachPrompt` (single prompt used by in-page drawer `Generate/Regenerate`)
- `RuleDefinition.source` includes `experienceHighlights` and `recentActivity`
- `ProspectSnapshot` includes optional `about`, `experienceHighlights`, `recentActivity`

## Storage keys

Defined in `src/lib/storage.ts`:

- `deal_copilot:settings`
- `deal_copilot:ui_collapsed`
- `deal_copilot:prospect:${encodeURIComponent(profileUrl)}`
- `deal_copilot:activity:${encodeURIComponent(profileUrl)}`

## Event taxonomy

Current activity event types:

- `SAVED`
- `GENERATED`
- `COPIED`
- `LOGGED_TOUCH`
- `STAGE_MOVED`
- `NOTE_ADDED`

MVP currently emits `SAVED`, `GENERATED`, and `COPIED`.
