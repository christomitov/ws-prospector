# Search Extraction

See also: [Sales Navigator URL Extractor](./sales-navigator.md), [API Reference](./API.md)

## Supported Search Sources

1. LinkedIn people search (`linkedin_search`)
2. Sales Navigator people search (`sales_navigator`)
3. Company people pages (`company_employees`)
4. Pasted URL source auto-detection (`/api/scrape-url`)

## LinkedIn People Search

Implementation:

1. Spider: `src/linkedin_leads/spiders/search.py`
2. Parser: `src/linkedin_leads/parsers/search_parser.py`
3. API route: `POST /api/search`

Query params used when present:

1. `page`
2. `keywords`
3. `titleFreeText`
4. `geoUrn`
5. `company`

## Company People Search

Implementation:

1. Spider: `src/linkedin_leads/spiders/company.py`
2. Parser: `src/linkedin_leads/parsers/company_parser.py`
3. API route: `POST /api/company-employees`

Behavior:

1. Requires `company` in request payload.
2. Builds `https://www.linkedin.com/company/{slug}/people/?page=...`.
3. Uses parser fallbacks to support multiple DOM variants.

## URL Mode (`/api/scrape-url`)

Implementation:

1. Spider: `src/linkedin_leads/spiders/url_scraper.py`
2. Source detection function: `detect_source(url)`

Detection rules:

1. URL containing `/sales/` -> `sales_navigator`
2. URL containing `/company/` and `/people` -> `company_employees`
3. Otherwise -> `linkedin_search`

Pagination behavior:

1. URL query is preserved.
2. `page=<n>` is inserted or replaced for each page.
3. Sales Navigator URLs run headless-first; if the captured HTML is loader-only (no lead rows), the scraper retries once in headed mode.
4. Stored `search_query` for URL mode is canonicalized by removing volatile params (`page`, `sessionId`, `_ntb`, `viewAllFilters`).

## CLI Collect Mode

Implementation:

1. Command: `ws-prospector-debug collect` (also `ws-prospector-cli collect` / `li-leads-cli collect`)
2. Module: `src/linkedin_leads/debug.py`
3. Profile enrichment: `src/linkedin_leads/profile_scraper.py`
4. Profile parser: `src/linkedin_leads/parsers/profile_parser.py`

Behavior:

1. Supports query mode (`--query`) and URL mode (`--sales-url` or `--url`).
2. Reuses existing search spiders, then optionally visits each profile URL.
3. Enrichment extracts summary/about, experience, education, and recent posts.
4. Outputs structured JSON plus flattened CSV for spreadsheet sharing.
5. Each collect run is recorded in SQLite `scrape_runs` with status/counts/output paths.
