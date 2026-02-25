# API Reference

Base URL: `http://127.0.0.1:8000`

All payloads and responses below reflect current implementation in `src/linkedin_leads/app.py`.

## Session

### `GET /api/session/status`
Returns current LinkedIn session status.

Response:
```json
{ "status": "connected|expired|unknown" }
```

### `POST /api/session/login`
Opens interactive login browser and updates saved profile session.

Response:
```json
{ "status": "connected|expired|unknown" }
```

## Search + Extraction

### Common request body (`SearchRequest`)
```json
{
  "keywords": "",
  "title": "",
  "location": "",
  "industry": "",
  "company": "",
  "max_pages": 5
}
```

`max_pages` is validated to `1..100`.

### `POST /api/search`
Starts LinkedIn people search extraction.

### `POST /api/search-navigator`
Starts Sales Navigator extraction.

### `POST /api/company-employees`
Starts company people extraction.

Notes:

- Requires `company` in request body.
- Returns `{ "error": "Company slug is required" }` if missing.

### `POST /api/scrape-url`
Starts extraction from pasted URL with source auto-detection.

Request:
```json
{
  "url": "https://www.linkedin.com/sales/search/people?...",
  "max_pages": 5
}
```

Detection logic:

- URL containing `/sales/` -> `sales_navigator`
- URL containing `/company/` and `/people` -> `company_employees`
- Otherwise -> `linkedin_search`

### Search start responses
When accepted:
```json
{ "status": "started", "source": "linkedin_search|sales_navigator|company_employees" }
```

If another search is running:
```json
{ "error": "A search is already running" }
```

### `GET /api/search/stream` (SSE)
Streams progress events:

- `status`: idle status when nothing is running
- `progress`: includes `found`, `page`, `done`, `error`
- `done`: terminal event for completed run

## Leads

### `GET /api/leads`
Query params:

- `source` (optional)
- `company` (optional substring filter)
- `search` (optional free-text across name/headline/title)
- `limit` (`1..1000`, default `100`)
- `offset` (`>=0`, default `0`)

Response:
```json
{
  "leads": [],
  "total": 0,
  "limit": 100,
  "offset": 0
}
```

### `GET /api/leads/export`
Query params:

- `format=csv|json` (default `csv`)
- `source` (optional)

Returns attachment (`leads.csv` or `leads.json`).

### `GET /api/stats`
Response:
```json
{
  "total": 0,
  "by_source": {
    "linkedin_search": 0,
    "sales_navigator": 0,
    "company_employees": 0
  },
  "last_scraped": null
}
```

## Auto Connector

### `POST /api/connect/enqueue`
Adds leads to connect queue.

Request:
```json
{
  "lead_ids": [1, 2, 3],
  "note": "Optional note"
}
```

Response:
```json
{
  "added": 3,
  "total_queued": 10
}
```

Notes:

- `added` counts newly inserted queue rows and failed rows reset back to pending for retry.

### Worker lifecycle

- `POST /api/connect/start`
- `POST /api/connect/stop`
- `POST /api/connect/pause`
- `POST /api/connect/resume`

Each returns worker status:
```json
{
  "running": false,
  "paused": false,
  "last_sent": null,
  "sends_today": 0,
  "daily_limit": 10,
  "pending": 0,
  "sent": 0,
  "failed": 0
}
```

### Queue visibility

### `GET /api/connect/status`
Returns worker status object (same shape as above).

### `GET /api/connect/queue`
Optional query: `status=pending|sent|failed`

Response:
```json
{
  "queue": [],
  "stats": {
    "pending": 0,
    "sent": 0,
    "failed": 0
  }
}
```

## Debug Endpoint

### `GET /api/debug/html/{page_num}`
Returns saved raw crawl HTML for selector troubleshooting.

If not found, returns `404` plain-text message.
