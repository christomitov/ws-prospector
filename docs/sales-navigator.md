# Sales Navigator URL Extractor

See also: [Search Extraction](./search-extraction.md), [API Reference](./API.md)

## What Is Supported

1. Form-driven Sales Nav extraction via `POST /api/search-navigator`
2. Pasted Sales Nav URL extraction via `POST /api/scrape-url`

## Core Implementation

1. Spider: `src/linkedin_leads/spiders/sales_nav.py`
2. URL source detection/pagination: `src/linkedin_leads/spiders/url_scraper.py`
3. Parser: `src/linkedin_leads/parsers/navigator_parser.py`

## URL Extractor Behavior

1. Any URL containing `/sales/` is treated as Sales Navigator source.
2. Existing query params are preserved.
3. `page` query param is replaced/inserted for pagination.
4. Sales Nav delay settings are applied (`SALES_NAV_DELAY`).

## Data Extracted Per Lead

1. `linkedin_url` (Sales lead URLs are preserved when normalization accepts them)
2. `full_name`
3. `headline`
4. `current_title`
5. `current_company`
6. `location`
7. `connection_degree`
8. `mutual_connections`
9. `source = sales_navigator`
10. `search_query`

## Known Constraints

1. Selector reliability depends on Sales Nav DOM changes.
2. Rate limiting and anti-automation responses can stop pagination early.
