# Agent Guide

This file tells coding agents where implementation details live.

## Primary Documentation

Start with:

1. `docs/README.md`

Then read feature-specific docs:

1. `docs/search-extraction.md`
2. `docs/sales-navigator.md`
3. `docs/auto-connector.md`
4. `docs/data-storage.md`
5. `docs/API.md`
6. `docs/architecture.md`
7. `docs/release-process.md`

## Source Of Truth

Documentation is descriptive. Code is authoritative.

Key implementation files:

1. API routes: `src/linkedin_leads/app.py`
2. Auto connector: `src/linkedin_leads/connect_worker.py`
3. URL/source detection: `src/linkedin_leads/spiders/url_scraper.py`
4. Search spiders: `src/linkedin_leads/spiders/search.py`, `src/linkedin_leads/spiders/sales_nav.py`, `src/linkedin_leads/spiders/company.py`
5. Parsers: `src/linkedin_leads/parsers/`
6. Storage and queue: `src/linkedin_leads/storage.py`
7. Session management: `src/linkedin_leads/auth/session_manager.py`

## Working Expectations

1. Keep docs aligned with actual behavior in code.
2. When changing connector logic, update `docs/auto-connector.md`.
3. When changing extraction or URL detection behavior, update `docs/search-extraction.md`.
4. When changing extraction or URL detection behavior, update `docs/sales-navigator.md`.
5. When endpoint contracts change, update `docs/API.md`.
6. Prefer adding small tests for parser/storage/connector behavior changes.
7. When release packaging or shipping steps change, update `docs/release-process.md`.
