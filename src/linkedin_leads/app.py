"""FastAPI application — API routes + serves frontend."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import webbrowser
import zipfile
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from sse_starlette.sse import EventSourceResponse

from .auth.session_manager import SessionManager
from .config import HOST, LOG_FILE, LOG_RETENTION_DAYS, LOG_DIR, PORT, ensure_dirs
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


def _list_log_files() -> list[Path]:
    ensure_dirs()
    files = [p for p in LOG_DIR.glob("server.log*") if p.is_file()]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _cleanup_old_logs() -> None:
    cutoff = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
    cutoff_ts = cutoff.timestamp()
    for path in _list_log_files():
        if path.stat().st_mtime < cutoff_ts:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.debug("Failed to delete old log file: %s", path)


def _configure_logging() -> None:
    ensure_dirs()
    _cleanup_old_logs()
    log_format = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    formatter = logging.Formatter(log_format)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    file_handler = TimedRotatingFileHandler(
        filename=str(LOG_FILE),
        when="midnight",
        interval=1,
        backupCount=LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logging.basicConfig(level=logging.INFO, handlers=[stream_handler, file_handler], force=True)


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

    run_id = store.create_scrape_run(
        run_type="api_search",
        source=source,
        query_text=req.keywords or req.company or "",
        max_pages=req.max_pages,
        params=req.model_dump(mode="json"),
    )
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
            store.update_scrape_run(run_id, status="completed", leads_found=len(leads), leads_enriched=0)
        except Exception as e:
            logger.exception("Spider failed")
            _active_search["error"] = str(e)
            _active_search["done"] = True
            store.update_scrape_run(run_id, status="failed", error=str(e))

    asyncio.create_task(run())
    return {"status": "started", "source": source, "run_id": run_id}


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

    run_id = store.create_scrape_run(
        run_type="api_scrape_url",
        source=source,
        input_url=url,
        max_pages=max_pages,
        params={"url": url, "max_pages": max_pages},
    )
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
            store.update_scrape_run(run_id, status="completed", leads_found=len(leads), leads_enriched=0)
        except Exception as e:
            logger.exception("URL scrape failed")
            _active_search["error"] = str(e)
            _active_search["done"] = True
            store.update_scrape_run(run_id, status="failed", error=str(e))

    asyncio.create_task(run())
    return {"status": "started", "source": source, "run_id": run_id}


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


@app.post("/api/leads/delete")
async def delete_leads(body: dict):
    lead_ids = body.get("lead_ids", [])
    if not isinstance(lead_ids, list) or not lead_ids:
        return {"error": "No lead_ids provided"}
    store = _get_store()
    deleted = store.delete_leads(lead_ids)
    return {"status": "ok", **deleted}


# ── Stats ─────────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def stats():
    store = _get_store()
    return store.stats()


@app.get("/api/runs")
async def list_runs(
    status: str | None = None,
    run_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    store = _get_store()
    runs = store.list_scrape_runs(status=status, run_type=run_type, limit=limit, offset=offset)
    total = store.count_scrape_runs(status=status, run_type=run_type)
    return {"runs": runs, "total": total, "limit": limit, "offset": offset}


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


@app.get("/api/settings/logs")
async def get_log_settings():
    _cleanup_old_logs()
    files = _list_log_files()
    return {
        "retention_days": LOG_RETENTION_DAYS,
        "total_size_bytes": sum(p.stat().st_size for p in files),
        "files": [
            {
                "name": p.name,
                "size_bytes": p.stat().st_size,
                "modified_at": datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat(),
            }
            for p in files
        ],
    }


@app.get("/api/settings/logs/download")
async def download_logs():
    _cleanup_old_logs()
    files = _list_log_files()
    if not files:
        return PlainTextResponse("No server logs available yet.", status_code=404)

    archive_name = f"wealthsimple-prospector-logs-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, arcname=path.name)
    payload.seek(0)
    return Response(
        content=payload.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{archive_name}"'},
    )


@app.post("/api/settings/logs/clear")
async def clear_logs():
    ensure_dirs()
    files = _list_log_files()
    removed_archives = 0
    truncated_current = False

    for path in files:
        if path == LOG_FILE:
            path.write_text("", encoding="utf-8")
            truncated_current = True
        else:
            path.unlink(missing_ok=True)
            removed_archives += 1

    if not LOG_FILE.exists():
        LOG_FILE.touch()

    return {
        "status": "ok",
        "removed_archives": removed_archives,
        "truncated_current": truncated_current,
    }


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
    _configure_logging()
    logger.info("Starting Wealthsimple Prospector at http://%s:%d", HOST, PORT)
    if os.getenv("WSP_OPEN_BROWSER", "1") not in {"0", "false", "False"}:
        webbrowser.open(f"http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info", log_config=None)
