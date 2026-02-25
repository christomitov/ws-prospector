---
name: linkedin-prospect-collector
description: Run end-to-end LinkedIn lead collection from search query or Sales Navigator URL, enrich each profile, and export structured JSON/CSV for downstream LLM qualification. Use when an agent needs to invoke repository-local CLI commands (via `uv run ...`) without requiring global PATH installation.
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
  --source sales_navigator \
  --max-pages 3 \
  --json-out out/leads.json \
  --csv-out out/leads.csv
```

3. Collect from Sales Navigator URL:

```bash
uv run ws-prospector-debug collect \
  --sales-url "https://www.linkedin.com/sales/search/people?..." \
  --max-pages 3 \
  --json-out out/leads.json \
  --csv-out out/leads.csv
```

## Flags

1. `--login-if-needed`: open LinkedIn login flow if session is expired.
2. `--fast`: skip experience/education/activity detail pages.
3. `--skip-enrich`: scrape search results only (no profile visits).
4. `--max-leads N`: hard cap on number of leads processed.
5. `--max-posts N`: recent activity snippets per profile.
6. `--no-store`: do not upsert leads into SQLite leads table.

## Output Contract

JSON output is an array of records:

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
    "recent_posts": [{ "url": "...", "text": "..." }],
    "errors": []
  },
  "collected_at": "2026-..."
}
```

CSV output is flattened for spreadsheet sharing.

## Agent Guidance

1. Prefer `uv run ws-prospector-debug collect ...` over assuming a global binary exists.
2. Use JSON for LLM evaluation and ranking.
3. Use CSV for sharing and QA review in Sheets.
4. If session is disconnected, rerun with `--login-if-needed`.
