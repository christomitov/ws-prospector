# Auto Connector

See also: [API Reference](./API.md), [Data Model And Storage](./data-storage.md)

## Purpose

Automatically process queued leads and send LinkedIn connection requests with throttling and daily limits.

## Core Implementation

1. Worker: `src/linkedin_leads/connect_worker.py`
2. Queue storage: `src/linkedin_leads/storage.py` (`connect_queue` table)
3. API controls in: `src/linkedin_leads/app.py`

## Queue Model

Queue items include:

1. `lead_id`
2. `linkedin_url`
3. `full_name`
4. `note`
5. `status` (`pending|sent|failed`)
6. `created_at`, `sent_at`
7. `error`

Dedup rule:

1. Unique by `linkedin_url` in queue.
2. Re-enqueueing a `failed` row resets it to `pending` (retry path).

## Worker Policy

1. Runs continuously by default (24/7).
2. Optional business-hours gate can be enabled via env vars.
3. Daily success cap defaults to `10` (based on sent items for the current local calendar day).
4. Random interval defaults to `90-300` seconds between attempts.
5. Uses browser lock to avoid profile conflicts with scraper/session checks.

## Configurable Limits

Connector pacing is configurable via environment variables:

1. `LI_CONNECT_DAILY_LIMIT` (default: `10`)
2. `LI_CONNECT_MIN_DELAY_SECONDS` (default: `90`)
3. `LI_CONNECT_MAX_DELAY_SECONDS` (default: `300`)
4. `LI_CONNECT_BUSINESS_HOURS_ONLY` (default: `0`)
5. `LI_CONNECT_BIZ_START_HOUR` (default: `9`)
6. `LI_CONNECT_BIZ_END_HOUR` (default: `17`)

## Send Flow

1. Open profile URL.
2. Skip when already pending/connected.
3. Find connect action in profile header or fallback menu.
4. Open invite path (direct URL or click).
5. Send via invite page or modal.
6. Verify post-send state.
7. Mark queue row as `sent` or `failed`.

## Debugging

Worker saves artifacts to `debug_html`:

1. `connect_1_loaded.png`, `connect_profile.html`
2. `connect_2_after_click.png`, `connect_after_click.html`
3. failure snapshots like `connect_fail_no_button.png`, `connect_fail_send.png`
