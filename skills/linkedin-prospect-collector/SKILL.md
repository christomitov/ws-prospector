---
name: linkedin-prospect-collector
description: Run end-to-end LinkedIn lead collection from search query or Sales Navigator URL, enrich profiles, and return structured stdout JSON/NDJSON (or JSON/CSV files) for downstream LLM qualification. Use when an agent needs to invoke repository-local CLI commands (via `uv run ...`) without requiring global PATH installation.
---

# LinkedIn Prospect Collector

Use this workflow from repository root (`/Users/christo/Work/linkedin-ws`).

## Commands

1. Check session status:

```bash
uv run ws-prospector-debug status
```

2. Collect from keyword query:

```bash
uv run ws-prospector-debug collect \
  --query "founder" \
  --source linkedin_search \
  --max-pages 3 \
  --stdout ndjson
```

3. Collect from Sales Navigator URL:

```bash
uv run ws-prospector-debug collect \
  --sales-url "https://www.linkedin.com/sales/search/people?..." \
  --max-pages 3 \
  --stdout json
```

4. Collect a specific person (caller-controlled mode):

```bash
uv run ws-prospector-debug collect \
  --query "Vriti Panwar" \
  --person-query \
  --fast \
  --stdout json \
  --output-view compact
```

Important:

1. Do not use `--query --source sales_navigator`; use `--sales-url` for Sales Nav targeting.
2. For Sales Navigator workflows, always build filters in Sales Nav UI first and pass the copied URL via `--sales-url`.
3. Caller decides mode; CLI does not auto-detect person intent. Use `--person-query` explicitly when needed.
4. Run `collect` jobs sequentially on the same machine/session. Parallel `collect` processes contend on Chromium's persistent profile lock (`user_data_dir`) and one run may fail.

## Flags

1. `--login-if-needed`: open LinkedIn login flow if session is expired.
2. `--fast`: skip detail subpages; still parse top-level profile sections from main profile page.
3. `--skip-enrich`: scrape search results only (no profile visits).
4. `--max-leads N`: hard cap on number of leads processed.
5. `--max-enriched N`: enrich only first N collected leads (0 = enrich all).
6. `--max-posts N`: featured/activity/recent snippets per profile.
7. `--person-query`: select and enrich best matching single profile from query results.
8. `--stdout json|csv|ndjson`: return output to stdout (preferred for agents).
9. `--output-view full|compact`: compact emits flat LLM-ready stdout records (JSON/NDJSON).
10. `--debug-html`: keep writing debug HTML snapshots (stdout mode disables them by default for speed).
11. `--no-store`: do not upsert leads into SQLite leads table.

## Output Contract

JSON output (`--stdout json` or `--json-out`) is an array of records:

```json
{
  "run_id": 123,
  "lead": { "full_name": "...", "linkedin_url": "...", "source": "..." },
  "profile": {
    "profile_url": "...",
    "summary": { "name": "...", "headline": "...", "location": "..." },
    "about": "...",
    "experience_items": ["..."],
    "education_items": ["..."],
    "certifications_items": ["..."],
    "volunteering_items": ["..."],
    "skills_items": ["..."],
    "honors_items": ["..."],
    "languages_items": ["..."],
    "featured_posts": [{ "url": "...", "text": "..." }],
    "activity_posts": [{ "url": "...", "text": "..." }],
    "recent_posts": [{ "url": "...", "text": "..." }],
    "errors": []
  },
  "collected_at": "2026-..."
}
```

`--stdout ndjson` emits one JSON record per line as each lead is processed (lowest latency for agent pipelines).
`--output-view compact` (stdout JSON/NDJSON) emits flattened records so callers do not need a jq normalization step.

CSV output is flattened for spreadsheet sharing when requested.

## Strict Qualification Policy

1. Treat CLI output as raw extraction only.
2. Always apply prompt-specific qualification after extraction.
3. Write final deliverable CSV with only candidates that meet the prompt criteria.
4. If no candidates meet criteria, still write CSV with headers and zero rows.
5. Do not include “maybe” candidates unless explicit evidence exists in extracted fields.

## Intent Parsing Rules

Before running commands, split user request into:

1. Search constraints:
   - role/title, location, company, industry, seniority.
   - pass these into search (query or Sales Nav URL).
2. Qualification constraints:
   - events/signals such as recent exit, acquisition, funding, hiring growth, etc.
   - do not push these into Sales Nav query unless explicitly required as a search filter.
   - evaluate these only from extracted profile data (`about`, `experience_items`, `recent_posts`, etc.).

Example:

1. Request: “CEO/CTO in Toronto likely to have had a recent exit/acquisition”
2. Search phase: CEO/CTO + Toronto.
3. Qualification phase: keep only profiles with explicit exit/acquisition signals.

## Agent Guidance

1. Prefer `uv run ws-prospector-debug collect ...` over assuming a global binary exists.
2. Prefer stdout (`--stdout ndjson` or `--stdout json --output-view compact`) for agent-to-agent pipelines; use files only when explicitly requested.
3. Use JSON for LLM evaluation and ranking.
4. Use CSV for sharing and QA review in Sheets.
5. If session is disconnected, rerun with `--login-if-needed`.
6. Parse user intent into two buckets before invoking CLI:
   - Search constraints (role/title, location, industry, company) -> CLI search inputs.
   - Qualification constraints (e.g., recent exit/acquisition/funding) -> downstream evaluation on enriched profile data.
7. For requests like "CEO/CTO in Toronto with recent exit":
   - Search with role/location only.
   - Do not include "recent exit" in the search query string.
   - Score/filter for exit signals using `profile.about`, `profile.experience_items`, `profile.featured_posts`, and `profile.activity_posts` after collection.
8. Final output rule: deliver only qualified rows in final CSV.
