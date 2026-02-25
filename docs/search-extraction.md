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
