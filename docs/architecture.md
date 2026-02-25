# Architecture

See also: [Data Model And Storage](./data-storage.md), [Auto Connector](./auto-connector.md)

## Main Components

1. FastAPI app: `src/linkedin_leads/app.py`
2. Session manager: `src/linkedin_leads/auth/session_manager.py`
3. Spiders:
   - `src/linkedin_leads/spiders/search.py`
   - `src/linkedin_leads/spiders/sales_nav.py`
   - `src/linkedin_leads/spiders/company.py`
   - `src/linkedin_leads/spiders/url_scraper.py`
4. Parsers:
   - `src/linkedin_leads/parsers/search_parser.py`
   - `src/linkedin_leads/parsers/navigator_parser.py`
   - `src/linkedin_leads/parsers/company_parser.py`
5. Storage: `src/linkedin_leads/storage.py`
6. Connect worker: `src/linkedin_leads/connect_worker.py`
7. Browser lock: `src/linkedin_leads/browser_lock.py`

## Runtime Behavior

1. Session status is checked via `/feed` using persistent profile cookies.
2. Searches are asynchronous jobs with SSE progress stream (`/api/search/stream`).
3. Only one search is allowed at a time (`_active_search` guard).
4. Leads are upserted to SQLite with deduplication.
5. Auto connector consumes queued leads in a background loop (24/7 by default, optional business-hours gate).

## Debug Artifacts

1. Crawl pages: `debug_html/page_{n}.html`
2. Connect worker screenshots and HTML snapshots: `debug_html/connect_*`
