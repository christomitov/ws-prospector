# AGENTS.md

## Documentation-first rule

All implementation work in this repository must reference and keep `docs/` current.

Before coding:

- Read `docs/README.md` and the relevant module/design docs.

When coding:

- Keep module boundaries and data contracts aligned with docs.

After coding:

- Update impacted docs in `docs/` in the same change.

## Docs map

- `docs/README.md` (entrypoint)
- `docs/architecture.md` (high-level architecture and runtime surfaces)
- `docs/modules.md` (module boundaries and responsibilities)
- `docs/data-model.md` (types, storage keys, event models)
- `docs/debugging.md` (live debug workflow + CLI tailing)
- `docs/roadmap.md` (milestones and current status)
