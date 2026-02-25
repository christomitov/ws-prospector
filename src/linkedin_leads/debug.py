"""CLI utility for diagnostics and data collection without the web UI.

Examples:
  uv run ws-prospector-debug status
  uv run ws-prospector-debug search --query "founder"
  uv run ws-prospector-debug collect --query "founder" --source sales_navigator
  uv run ws-prospector-debug collect --sales-url "https://www.linkedin.com/sales/search/people?..."
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR, ensure_dirs

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEBUG_HTML_DIR = DATA_DIR / "debug_html"


def cmd_status() -> None:
    from .auth.session_manager import SessionManager

    mgr = SessionManager()
    status = asyncio.run(mgr.check_status())
    print(f"Session: {status.value}")


def cmd_html(page_num: int = 1) -> None:
    path = DEBUG_HTML_DIR / f"page_{page_num}.html"
    if not path.exists():
        print(f"No debug HTML at {path}. Run a search first.")
        return

    content = path.read_text(encoding="utf-8")
    print(f"File: {path}")
    print(f"Size: {len(content):,} bytes")

    cards = len(re.findall(r'data-view-name="people-search-result"', content))
    links = len(re.findall(r'href="https://www.linkedin.com/in/[^"]+', content))
    titles = len(re.findall(r'data-view-name="search-result-lockup-title"', content))
    print(f"Result cards (data-view-name): {cards}")
    print(f"Profile links: {links}")
    print(f"Title elements: {titles}")

    starts = [m.start() for m in re.finditer(r'data-view-name="people-search-result"', content)]
    for i, s in enumerate(starts):
        div_start = content.rfind("<div", 0, s)
        if i + 1 < len(starts):
            div_end = content.rfind("<div", 0, starts[i + 1])
        else:
            div_end = min(len(content), div_start + 8000)
        card = content[div_start:div_end]
        texts = re.findall(r">([^<]{2,})<", card)
        texts = [t.strip() for t in texts if t.strip() and not t.strip().startswith("{")]
        name = texts[0] if texts else "?"
        print(f"\n  Card {i+1}: {name}")
        print(f"    Text: {texts[:8]}")


def cmd_parse(page_num: int = 1) -> None:
    from scrapling.parser import Adaptor

    from .parsers.search_parser import parse_search_results

    path = DEBUG_HTML_DIR / f"page_{page_num}.html"
    if not path.exists():
        print(f"No debug HTML at {path}. Run a search first.")
        return

    html = path.read_text(encoding="utf-8")
    page = Adaptor(html, url="https://www.linkedin.com/search/results/people/")
    leads = parse_search_results(page, search_query="debug")

    print(f"Parsed {len(leads)} leads from {path.name}:")
    for i, lead in enumerate(leads, 1):
        print(f"\n  {i}. {lead.full_name}")
        print(f"     URL:     {lead.linkedin_url}")
        print(f"     Title:   {lead.current_title}")
        print(f"     Company: {lead.current_company}")
        print(f"     Location:{lead.location}")
        print(f"     Degree:  {lead.connection_degree}")
        print(f"     Mutual:  {lead.mutual_connections}")


def cmd_search(query: str, *, source: str = "linkedin_search", max_pages: int = 1) -> None:
    from .auth.session_manager import SessionManager
    from .models import SearchRequest
    from .spiders.sales_nav import SalesNavigatorSpider
    from .spiders.search import LinkedInSearchSpider
    from .storage import LeadStore

    mgr = SessionManager()
    req = SearchRequest(keywords=query, max_pages=max_pages)
    if source == "sales_navigator":
        spider = SalesNavigatorSpider(mgr.user_data_dir, req, max_pages=max_pages)
    else:
        spider = LinkedInSearchSpider(mgr.user_data_dir, req, max_pages=max_pages)

    async def run() -> list:
        async def on_progress(found: int, page: int) -> None:
            print(f"  Page {page}: {found} leads so far...")

        return await spider.crawl(on_progress=on_progress)

    print(f"Searching for: {query} ({source})")
    leads = asyncio.run(run())
    print(f"\nFound {len(leads)} leads:")
    for i, lead in enumerate(leads, 1):
        print(f"  {i}. {lead.full_name} — {lead.headline} ({lead.location})")
        if lead.linkedin_url:
            print(f"     {lead.linkedin_url}")

    if leads:
        store = LeadStore()
        store.upsert_many(leads)
        print(f"\nSaved {len(leads)} leads to database.")


def _lead_to_dict(lead: object) -> dict:
    if hasattr(lead, "model_dump"):
        data = lead.model_dump(mode="json")
    else:
        data = dict(lead)
    scraped = data.get("scraped_at")
    if hasattr(scraped, "isoformat"):
        data["scraped_at"] = scraped.isoformat()
    return data


def _trim(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    value = re.sub(r"\s+", " ", text).strip()
    return value[:max_chars]


def _join_preview(values: list[str], *, limit: int = 3, max_chars: int = 180) -> str:
    out = [_trim(v, max_chars) for v in values[:limit] if v]
    return " | ".join(v for v in out if v)


def _flatten_csv_row(record: dict) -> dict:
    lead = record.get("lead", {})
    profile = record.get("profile", {})
    posts = profile.get("recent_posts") or []
    post_texts = [p.get("text", "") for p in posts if isinstance(p, dict)]

    return {
        "run_id": record.get("run_id"),
        "full_name": lead.get("full_name"),
        "linkedin_url": lead.get("linkedin_url"),
        "profile_url": profile.get("profile_url"),
        "source": lead.get("source"),
        "search_query": lead.get("search_query"),
        "headline": lead.get("headline"),
        "current_title": lead.get("current_title"),
        "current_company": lead.get("current_company"),
        "location": lead.get("location"),
        "connection_degree": lead.get("connection_degree"),
        "mutual_connections": lead.get("mutual_connections"),
        "about": _trim(profile.get("about"), 4000),
        "experience_count": len(profile.get("experience_items") or []),
        "experience_preview": _join_preview(profile.get("experience_items") or []),
        "education_count": len(profile.get("education_items") or []),
        "education_preview": _join_preview(profile.get("education_items") or []),
        "recent_posts_count": len(posts),
        "recent_posts_preview": _join_preview(post_texts, max_chars=240),
        "enrichment_errors": " | ".join(profile.get("errors") or []),
        "collected_at": record.get("collected_at"),
    }


def _default_output_paths(prefix: str) -> tuple[Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = f"{prefix}-{stamp}"
    return Path(f"{stem}.json"), Path(f"{stem}.csv")


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_csv(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_flatten_csv_row(r) for r in records]
    fieldnames = [
        "run_id",
        "full_name",
        "linkedin_url",
        "profile_url",
        "source",
        "search_query",
        "headline",
        "current_title",
        "current_company",
        "location",
        "connection_degree",
        "mutual_connections",
        "about",
        "experience_count",
        "experience_preview",
        "education_count",
        "education_preview",
        "recent_posts_count",
        "recent_posts_preview",
        "enrichment_errors",
        "collected_at",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


async def _collect_async(args: argparse.Namespace) -> int:
    from .auth.session_manager import SessionManager, SessionStatus
    from .models import SearchRequest
    from .profile_scraper import enrich_profile
    from .spiders.sales_nav import SalesNavigatorSpider
    from .spiders.search import LinkedInSearchSpider
    from .spiders.url_scraper import UrlSpider
    from .storage import LeadStore

    mgr = SessionManager()
    status = await mgr.check_status()
    if status != SessionStatus.connected and args.login_if_needed:
        print("Session not connected. Opening LinkedIn login...")
        status = await mgr.login()

    if status != SessionStatus.connected:
        print("LinkedIn session is not connected. Run `ws-prospector-debug status` or `--login-if-needed`.")
        return 2

    if args.sales_url or args.url:
        input_url = args.sales_url or args.url
        spider = UrlSpider(mgr.user_data_dir, input_url, max_pages=args.max_pages)
        source = spider._source.value
        query_text = input_url
        run_params = {
            "mode": "url",
            "input_url": input_url,
            "max_pages": args.max_pages,
            "max_leads": args.max_leads,
            "skip_enrich": args.skip_enrich,
        }
    else:
        req = SearchRequest(
            keywords=args.query or "",
            title=args.title or "",
            location=args.location or "",
            industry=args.industry or "",
            company=args.company or "",
            max_pages=args.max_pages,
        )
        source = args.source
        if source == "sales_navigator":
            spider = SalesNavigatorSpider(mgr.user_data_dir, req, max_pages=args.max_pages)
        else:
            spider = LinkedInSearchSpider(mgr.user_data_dir, req, max_pages=args.max_pages)
        query_text = req.keywords
        input_url = None
        run_params = {
            "mode": "query",
            "source": source,
            "request": req.model_dump(mode="json"),
            "max_leads": args.max_leads,
            "skip_enrich": args.skip_enrich,
        }

    store = LeadStore()
    run_id = store.create_scrape_run(
        run_type="cli_collect",
        status="running",
        source=source,
        query_text=query_text,
        input_url=input_url,
        max_pages=args.max_pages,
        params=run_params,
    )

    try:
        print(f"Starting run #{run_id} ({source})")

        async def on_progress(found: int, page: int) -> None:
            print(f"  Search page {page}: {found} leads so far")

        leads = await spider.crawl(on_progress=on_progress)
        if args.max_leads and len(leads) > args.max_leads:
            leads = leads[: args.max_leads]
            print(f"Trimmed to max leads: {args.max_leads}")

        if args.store and leads:
            store.upsert_many(leads)

        collected_at = datetime.now(timezone.utc).isoformat()
        records: list[dict] = []
        enriched_count = 0

        for idx, lead in enumerate(leads, 1):
            lead_dict = _lead_to_dict(lead)
            print(f"  [{idx}/{len(leads)}] {lead.full_name}")
            if args.skip_enrich:
                profile_payload = {
                    "profile_url": lead.linkedin_url,
                    "summary": {},
                    "about": None,
                    "experience_items": [],
                    "education_items": [],
                    "recent_posts": [],
                    "errors": ["Skipped enrichment (remove --skip-enrich to enrich profiles)"],
                }
            else:
                profile_payload = await enrich_profile(
                    mgr.user_data_dir,
                    lead.linkedin_url,
                    max_posts=args.max_posts,
                    include_details=not args.fast,
                )
                if profile_payload.get("profile_url"):
                    enriched_count += 1

            records.append(
                {
                    "run_id": run_id,
                    "lead": lead_dict,
                    "profile": profile_payload,
                    "collected_at": collected_at,
                }
            )

        json_out = Path(args.json_out) if args.json_out else None
        csv_out = Path(args.csv_out) if args.csv_out else None
        if not json_out and not csv_out:
            json_out, csv_out = _default_output_paths("lead-collection")

        if json_out:
            _write_json(json_out, records)
        if csv_out:
            _write_csv(csv_out, records)

        store.update_scrape_run(
            run_id,
            status="completed",
            leads_found=len(leads),
            leads_enriched=enriched_count,
            json_output_path=str(json_out) if json_out else None,
            csv_output_path=str(csv_out) if csv_out else None,
            params_json=run_params,
        )

        print(f"Completed run #{run_id}.")
        print(f"Leads found: {len(leads)}")
        print(f"Profiles enriched: {enriched_count}")
        if json_out:
            print(f"JSON output: {json_out}")
        if csv_out:
            print(f"CSV output: {csv_out}")
        return 0
    except Exception as exc:
        store.update_scrape_run(
            run_id,
            status="failed",
            error=str(exc),
            params_json=run_params,
        )
        raise


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ws-prospector-debug",
        description="Debug + extraction CLI for Wealthsimple Prospector.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Check LinkedIn session status.")

    html = sub.add_parser("html", help="Summarize saved debug HTML page.")
    html.add_argument("page", nargs="?", type=int, default=1, help="Page number in debug_html/page_<N>.html")

    parse = sub.add_parser("parse", help="Parse a saved debug HTML page with search parser.")
    parse.add_argument("page", nargs="?", type=int, default=1, help="Page number in debug_html/page_<N>.html")

    search = sub.add_parser("search", help="Run one-off search scrape and print/store leads.")
    search.add_argument("--query", required=True, help="Search query string.")
    search.add_argument(
        "--source",
        choices=["linkedin_search", "sales_navigator"],
        default="linkedin_search",
        help="Search source when using --query (default: linkedin_search).",
    )
    search.add_argument("--max-pages", type=int, default=1, help="Max pages to scrape (1-100).")

    collect = sub.add_parser(
        "collect",
        help="Collect leads + profile enrichment to JSON/CSV for downstream LLM evaluation.",
        description=(
            "Run a lead collection workflow and export structured profile data.\n\n"
            "Modes:\n"
            "  1) Query mode: pass --query with --source linkedin_search|sales_navigator\n"
            "  2) URL mode: pass --sales-url (or --url) with a LinkedIn/Sales Nav search link"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  ws-prospector-debug collect --query \"founder\" --source sales_navigator --max-pages 3\n"
            "  ws-prospector-debug collect --sales-url \"https://www.linkedin.com/sales/search/people?...\"\n"
            "  ws-prospector-debug collect --query \"head of partnerships\" --json-out out/leads.json --csv-out out/leads.csv\n\n"
            "Output contract:\n"
            "  - JSON: array of records { run_id, lead, profile, collected_at }\n"
            "  - CSV: flattened columns for easy spreadsheet sharing"
        ),
    )
    mode = collect.add_mutually_exclusive_group(required=True)
    mode.add_argument("--query", help="Keywords to search for.")
    mode.add_argument("--sales-url", help="Sales Navigator people search URL.")
    mode.add_argument("--url", help="Generic LinkedIn search URL (auto-detects source).")
    collect.add_argument(
        "--source",
        choices=["linkedin_search", "sales_navigator"],
        default="linkedin_search",
        help="Search source for --query mode (default: linkedin_search).",
    )
    collect.add_argument("--title", default="", help="Title filter (query mode).")
    collect.add_argument("--location", default="", help="Location filter (query mode).")
    collect.add_argument("--industry", default="", help="Industry filter (query mode, Sales Nav).")
    collect.add_argument("--company", default="", help="Company filter (query mode).")
    collect.add_argument("--max-pages", type=int, default=5, help="Max result pages to scrape (1-100).")
    collect.add_argument("--max-leads", type=int, default=150, help="Hard cap on total leads processed.")
    collect.add_argument("--max-posts", type=int, default=5, help="Max recent post snippets per profile.")
    collect.add_argument(
        "--fast",
        action="store_true",
        help="Fast mode: only fetch profile main page (skip experience/education/activity subpages).",
    )
    collect.add_argument(
        "--skip-enrich",
        action="store_true",
        help="Skip profile visits and only output search result fields.",
    )
    collect.add_argument("--json-out", default="", help="Path for JSON output (default: auto timestamped file).")
    collect.add_argument("--csv-out", default="", help="Path for CSV output (default: auto timestamped file).")
    collect.add_argument(
        "--no-store",
        action="store_true",
        help="Do not upsert collected leads into SQLite leads table.",
    )
    collect.add_argument(
        "--login-if-needed",
        action="store_true",
        help="Automatically open LinkedIn login if session is not connected.",
    )

    return parser


def main() -> None:
    ensure_dirs()
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "status":
        cmd_status()
        return
    if args.command == "html":
        cmd_html(args.page)
        return
    if args.command == "parse":
        cmd_parse(args.page)
        return
    if args.command == "search":
        max_pages = max(1, min(int(args.max_pages), 100))
        cmd_search(args.query, source=args.source, max_pages=max_pages)
        return
    if args.command == "collect":
        args.max_pages = max(1, min(int(args.max_pages), 100))
        args.max_leads = max(1, int(args.max_leads))
        args.max_posts = max(1, int(args.max_posts))
        args.store = not args.no_store
        raise SystemExit(asyncio.run(_collect_async(args)))

    parser.print_help()
