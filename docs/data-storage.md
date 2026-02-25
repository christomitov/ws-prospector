# Data Model And Storage

See also: [API Reference](./API.md), [Architecture](./architecture.md)

## Lead Model

Implementation: `src/linkedin_leads/models.py`

Fields:

1. `linkedin_url`
2. `full_name`
3. `headline`
4. `current_title`
5. `current_company`
6. `location`
7. `connection_degree`
8. `mutual_connections`
9. `source`
10. `search_query`
11. `scraped_at`

Normalization:

1. LinkedIn URLs are normalized to canonical host and stripped of query params.
2. Dedup key uses URL when present; otherwise `full_name|current_company`.

## SQLite Storage

Implementation: `src/linkedin_leads/storage.py`

Tables:

1. `leads`
2. `connect_queue`
3. `scrape_runs`

Lead upsert behavior:

1. `dedup_key` is unique.
2. Existing rows are updated with non-null incoming fields.

Exports:

1. CSV export via `/api/leads/export?format=csv`
2. JSON export via `/api/leads/export?format=json`

Scrape run history:

1. API and CLI scrape jobs are stored in `scrape_runs` with status and timestamps.
2. Tracks source, query/url input, found/enriched counts, error text, and JSON/CSV output paths.

## Runtime Paths

Configured in: `src/linkedin_leads/config.py`

1. Data root: `platformdirs.user_data_dir("wealthsimple-prospector")`
2. DB file: `leads.db`
3. Session dir: `sessions/`
4. Crawl/debug data: `crawldata/` and `debug_html/`

Branding note:

1. New app name uses `platformdirs.user_data_dir("wealthsimple-prospector")`.
2. If legacy `linkedin-leads` data exists and the new directory does not, the app automatically uses the legacy directory to preserve existing data.
