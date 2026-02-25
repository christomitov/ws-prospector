# Sales Navigator URL Extractor

See also: [Search Extraction](./search-extraction.md), [API Reference](./API.md)

## What Is Supported

1. Form-driven Sales Nav extraction via `POST /api/search-navigator`
2. Pasted Sales Nav URL extraction via `POST /api/scrape-url`
3. CLI-driven Sales Nav collection via `ws-prospector-debug collect --sales-url ...`

## Core Implementation

1. Spider: `src/linkedin_leads/spiders/sales_nav.py`
2. URL source detection/pagination: `src/linkedin_leads/spiders/url_scraper.py`
3. Parser: `src/linkedin_leads/parsers/navigator_parser.py`

## URL Extractor Behavior

1. Any URL containing `/sales/` is treated as Sales Navigator source.
2. Existing query params are preserved.
3. `page` query param is replaced/inserted for pagination.
4. Sales Nav delay settings are applied (`SALES_NAV_DELAY`).
5. Fetching is headless-first; if Sales Nav returns only the loading skeleton (no lead rows in HTML), the scraper retries once in headed mode.
6. The page action waits for JS-rendered Sales Nav lead rows before parsing.

## Data Extracted Per Lead

1. `linkedin_url` (Sales lead URLs are normalized to absolute `https://www.linkedin.com/sales/lead/...` links)
2. `full_name`
3. `headline`
4. `current_title`
5. `current_company`
6. `location`
7. `connection_degree`
8. `mutual_connections`
9. `source = sales_navigator`
10. `search_query` (URL-mode canonicalized to remove volatile params like `sessionId`/`page`)

## Known Constraints

1. Selector reliability depends on Sales Nav DOM changes.
2. Rate limiting and anti-automation responses can stop pagination early.
3. Sales Nav uses JS-rendered content; if your environment cannot open a headed browser window when fallback is required, extraction may return zero rows.
4. Some Sales lead URLs do not directly expose `/in/` profile URLs; CLI enrichment resolves profile URLs best-effort and may leave unresolved leads when profile links are not present in fetched HTML.
