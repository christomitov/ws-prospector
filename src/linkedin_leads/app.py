"""FastAPI application — API routes + serves frontend."""

from __future__ import annotations

import asyncio
import logging
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from sse_starlette.sse import EventSourceResponse

from .auth.session_manager import SessionManager
from .config import HOST, PORT, ensure_dirs
from .connect_worker import ConnectWorker
from .models import LeadSource, SearchRequest
from .spiders.company import CompanyEmployeesSpider
from .spiders.sales_nav import SalesNavigatorSpider
from .spiders.search import LinkedInSearchSpider
from .spiders.url_scraper import UrlSpider
from .storage import LeadStore

logger = logging.getLogger(__name__)

app = FastAPI(title="Wealthsimple Prospector", version="0.1.0")

# Singletons — initialized at startup
_session_mgr: SessionManager | None = None
_store: LeadStore | None = None
_active_search: dict | None = None
_connect_worker: ConnectWorker | None = None


def _get_connect_worker() -> ConnectWorker:
    global _connect_worker
    if _connect_worker is None:
        _connect_worker = ConnectWorker(_get_session().user_data_dir, _get_store())
    return _connect_worker

FRONTEND_DIR = Path(__file__).parent / "frontend"


def _get_session() -> SessionManager:
    global _session_mgr
    if _session_mgr is None:
        _session_mgr = SessionManager()
    return _session_mgr


def _get_store() -> LeadStore:
    global _store
    if _store is None:
        _store = LeadStore()
    return _store


# ── Frontend ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


# ── Session ───────────────────────────────────────────────────────────────

@app.get("/api/session/status")
async def session_status():
    mgr = _get_session()
    status = await mgr.check_status()
    return {"status": status.value}


@app.post("/api/session/login")
async def session_login():
    mgr = _get_session()
    status = await mgr.login()
    return {"status": status.value}


@app.post("/api/session/logout")
async def session_logout():
    mgr = _get_session()
    worker = _get_connect_worker()
    worker.stop()
    status = await mgr.logout()
    return {"status": status.value}


# ── Search ────────────────────────────────────────────────────────────────

@app.post("/api/search")
async def start_search(req: SearchRequest):
    return await _run_spider("linkedin_search", req)


@app.post("/api/search-navigator")
async def start_navigator_search(req: SearchRequest):
    return await _run_spider("sales_navigator", req)


@app.post("/api/company-employees")
async def start_company_search(req: SearchRequest):
    if not req.company:
        return {"error": "Company slug is required"}, 400
    return await _run_spider("company_employees", req)


async def _run_spider(source: str, req: SearchRequest) -> dict:
    global _active_search
    if _active_search and not _active_search.get("done"):
        return {"error": "A search is already running"}

    mgr = _get_session()
    store = _get_store()

    # Build spider
    if source == "linkedin_search":
        spider = LinkedInSearchSpider(mgr.user_data_dir, req, max_pages=req.max_pages)
    elif source == "sales_navigator":
        spider = SalesNavigatorSpider(mgr.user_data_dir, req, max_pages=req.max_pages)
    else:
        spider = CompanyEmployeesSpider(mgr.user_data_dir, req, max_pages=req.max_pages)

    _active_search = {"found": 0, "page": 0, "done": False, "error": None}

    async def run():
        try:
            async def on_progress(found: int, page: int):
                _active_search["found"] = found
                _active_search["page"] = page

            leads = await spider.crawl(on_progress=on_progress)
            if leads:
                store.upsert_many(leads)
            _active_search["found"] = len(leads)
            _active_search["done"] = True
        except Exception as e:
            logger.exception("Spider failed")
            _active_search["error"] = str(e)
            _active_search["done"] = True

    asyncio.create_task(run())
    return {"status": "started", "source": source}


@app.post("/api/scrape-url")
async def scrape_url(body: dict):
    """Scrape leads from a pasted LinkedIn URL (search, Sales Nav, or company page)."""
    global _active_search
    if _active_search and not _active_search.get("done"):
        return {"error": "A search is already running"}

    url = body.get("url", "").strip()
    if not url or "linkedin.com" not in url:
        return {"error": "Please provide a valid LinkedIn URL"}

    max_pages = body.get("max_pages", 5)
    mgr = _get_session()
    store = _get_store()

    spider = UrlSpider(mgr.user_data_dir, url, max_pages=max_pages)
    source = spider._source.value

    _active_search = {"found": 0, "page": 0, "done": False, "error": None}

    async def run():
        try:
            async def on_progress(found: int, page: int):
                _active_search["found"] = found
                _active_search["page"] = page

            leads = await spider.crawl(on_progress=on_progress)
            if leads:
                store.upsert_many(leads)
            _active_search["found"] = len(leads)
            _active_search["done"] = True
        except Exception as e:
            logger.exception("URL scrape failed")
            _active_search["error"] = str(e)
            _active_search["done"] = True

    asyncio.create_task(run())
    return {"status": "started", "source": source}


@app.get("/api/search/stream")
async def search_stream(request: Request):
    """SSE endpoint streaming search progress."""

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            if _active_search is None:
                yield {"event": "status", "data": '{"idle": true}'}
                await asyncio.sleep(1)
                continue

            import json
            yield {"event": "progress", "data": json.dumps(_active_search)}

            if _active_search.get("done"):
                yield {"event": "done", "data": json.dumps(_active_search)}
                break

            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


# ── Leads ─────────────────────────────────────────────────────────────────

@app.get("/api/leads")
async def list_leads(
    source: str | None = None,
    company: str | None = None,
    search: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    store = _get_store()
    lead_source = LeadSource(source) if source else None
    rows = store.query(source=lead_source, company=company, search=search, limit=limit, offset=offset)
    total = store.count(source=lead_source)
    return {"leads": rows, "total": total, "limit": limit, "offset": offset}


@app.get("/api/leads/export")
async def export_leads(
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    source: str | None = None,
):
    store = _get_store()
    lead_source = LeadSource(source) if source else None
    if format == "json":
        data = store.export_json(source=lead_source)
        return Response(
            content=data,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=leads.json"},
        )
    data = store.export_csv(source=lead_source)
    return Response(
        content=data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@app.post("/api/leads/clear")
async def clear_leads():
    store = _get_store()
    worker = _get_connect_worker()
    worker.stop()
    deleted = store.clear_leads()
    return {"status": "ok", **deleted}


# ── Stats ─────────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def stats():
    store = _get_store()
    return store.stats()


# ── Connect Queue ─────────────────────────────────────────────────────────

@app.post("/api/connect/enqueue")
async def enqueue_connects(body: dict):
    """Add leads to the connect request queue."""
    lead_ids = body.get("lead_ids", [])
    note = body.get("note")
    if not lead_ids:
        return {"error": "No lead IDs provided"}
    store = _get_store()
    added = store.enqueue_connects(lead_ids, note=note)
    return {"added": added, "total_queued": store.connect_queue_stats()["pending"]}


@app.post("/api/connect/retry")
async def retry_connect(body: dict):
    """Retry a failed connect immediately by re-queueing and waking worker."""
    lead_id = body.get("lead_id")
    if not lead_id:
        return {"error": "No lead_id provided"}

    store = _get_store()
    added = store.enqueue_connects([int(lead_id)], note=body.get("note"))
    worker = _get_connect_worker()
    if added > 0:
        if not worker.is_running:
            worker.start()
        worker.nudge()

    return {
        "added": added,
        "running": worker.is_running,
        "queue": store.connect_queue_stats(),
    }


@app.post("/api/connect/start")
async def start_connect_worker():
    """Start the background connect worker."""
    worker = _get_connect_worker()
    worker.start()
    return worker.status()


@app.post("/api/connect/stop")
async def stop_connect_worker():
    """Stop the background connect worker."""
    worker = _get_connect_worker()
    worker.stop()
    return worker.status()


@app.post("/api/connect/pause")
async def pause_connect_worker():
    worker = _get_connect_worker()
    worker.pause()
    return worker.status()


@app.post("/api/connect/resume")
async def resume_connect_worker():
    worker = _get_connect_worker()
    worker.resume()
    return worker.status()


@app.get("/api/connect/status")
async def connect_status():
    worker = _get_connect_worker()
    return worker.status()


@app.get("/api/connect/queue")
async def connect_queue(status: str | None = None):
    store = _get_store()
    items = store.connect_queue_list(status=status)
    return {"queue": items, "stats": store.connect_queue_stats()}


# ── Settings ─────────────────────────────────────────────────────────────

@app.get("/api/settings/connect")
async def get_connect_settings():
    worker = _get_connect_worker()
    return worker.get_settings()


@app.put("/api/settings/connect")
async def update_connect_settings(body: dict):
    allowed = {
        "daily_limit",
        "min_delay_seconds",
        "max_delay_seconds",
        "business_hours_only",
        "biz_start_hour",
        "biz_end_hour",
    }
    updates = {k: v for k, v in body.items() if k in allowed}
    worker = _get_connect_worker()
    return worker.update_settings(updates)


# ── Debug ─────────────────────────────────────────────────────────────────

@app.get("/api/debug/html/{page_num}")
async def debug_html(page_num: int):
    """View raw HTML from last crawl for debugging selectors."""
    from .spiders.base import DEBUG_HTML_DIR

    path = DEBUG_HTML_DIR / f"page_{page_num}.html"
    if not path.exists():
        return PlainTextResponse("No debug HTML saved yet. Run a search first.", status_code=404)
    return HTMLResponse(path.read_text(encoding="utf-8"))


# ── Entrypoint ────────────────────────────────────────────────────────────

def main():
    """CLI entrypoint: start server and open browser."""
    ensure_dirs()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Starting Wealthsimple Prospector at http://%s:%d", HOST, PORT)
    webbrowser.open(f"http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
