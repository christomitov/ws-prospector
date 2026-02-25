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
import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR, ensure_dirs
from .run_labels import summarize_request, summarize_url

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEBUG_HTML_DIR = DATA_DIR / "debug_html"


def validate_collect_mode(args: argparse.Namespace) -> tuple[bool, str | None]:
    """Validate collect mode combinations before opening browser sessions."""
    if args.query and args.source == "sales_navigator":
        return (
            False,
            "collect: Sales Navigator query mode is not supported reliably.\n"
            "Use --sales-url with a URL copied from Sales Navigator after applying filters.",
        )
    return True, None


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


def _tokenize_name(text: str | None) -> list[str]:
    raw = (text or "").split(",", 1)[0]
    return [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z'’-]*", raw)]


def _person_match_score(query: str, lead_name: str | None) -> int:
    q = _tokenize_name(query)
    n = _tokenize_name(lead_name)
    if not q or not n:
        return 0
    if q == n:
        return 100
    overlap = len(set(q).intersection(n))
    score = overlap * 20
    if q and n and q[0] == n[0]:
        score += 10
    if len(q) > 1 and len(n) > 1 and q[-1] == n[-1]:
        score += 10
    return score


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
    source_url = lead.get("linkedin_url")
    resolved_profile_url = profile.get("profile_url")
    primary_url = resolved_profile_url or source_url
    posts = profile.get("recent_posts") or []
    featured_posts = profile.get("featured_posts") or []
    activity_posts = profile.get("activity_posts") or []
    post_texts = [p.get("text", "") for p in posts if isinstance(p, dict)]
    featured_texts = [p.get("text", "") for p in featured_posts if isinstance(p, dict)]
    activity_texts = [p.get("text", "") for p in activity_posts if isinstance(p, dict)]

    return {
        "run_id": record.get("run_id"),
        "full_name": lead.get("full_name"),
        "linkedin_url": primary_url,
        "profile_url": resolved_profile_url,
        "source_url": source_url,
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
        "certifications_count": len(profile.get("certifications_items") or []),
        "certifications_preview": _join_preview(profile.get("certifications_items") or []),
        "volunteering_count": len(profile.get("volunteering_items") or []),
        "volunteering_preview": _join_preview(profile.get("volunteering_items") or []),
        "skills_count": len(profile.get("skills_items") or []),
        "skills_preview": _join_preview(profile.get("skills_items") or []),
        "honors_count": len(profile.get("honors_items") or []),
        "honors_preview": _join_preview(profile.get("honors_items") or []),
        "languages_count": len(profile.get("languages_items") or []),
        "languages_preview": _join_preview(profile.get("languages_items") or []),
        "featured_posts_count": len(featured_posts),
        "featured_posts_preview": _join_preview(featured_texts, max_chars=240),
        "activity_posts_count": len(activity_posts),
        "activity_posts_preview": _join_preview(activity_texts, max_chars=240),
        "recent_posts_count": len(posts),
        "recent_posts_preview": _join_preview(post_texts, max_chars=240),
        "enrichment_errors": " | ".join(profile.get("errors") or []),
        "collected_at": record.get("collected_at"),
    }


def _dedupe_trimmed(values: list[str], *, max_items: int = 8, max_chars: int = 260) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _trim(value, max_chars)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
        if len(out) >= max_items:
            break
    return out


def _compact_posts(
    posts: list[dict],
    *,
    max_items: int = 5,
    max_chars: int = 260,
) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for post in posts:
        if not isinstance(post, dict):
            continue
        url = post.get("url")
        text = _trim(post.get("text"), max_chars)
        key = f"{url}|{text}"
        if not text or key in seen:
            continue
        seen.add(key)
        out.append({"url": url, "text": text})
        if len(out) >= max_items:
            break
    return out


def _compact_record(record: dict) -> dict:
    lead = record.get("lead", {})
    profile = record.get("profile", {})
    return {
        "run_id": record.get("run_id"),
        "collected_at": record.get("collected_at"),
        "name": lead.get("full_name"),
        "linkedin_url": profile.get("profile_url") or lead.get("linkedin_url"),
        "source_url": lead.get("linkedin_url"),
        "headline": lead.get("headline"),
        "title": lead.get("current_title"),
        "company": lead.get("current_company"),
        "location": lead.get("location"),
        "connection_degree": lead.get("connection_degree"),
        "mutual_connections": lead.get("mutual_connections"),
        "about": _trim(profile.get("about"), 1600),
        "experience": _dedupe_trimmed(profile.get("experience_items") or []),
        "education": _dedupe_trimmed(profile.get("education_items") or []),
        "certifications": _dedupe_trimmed(profile.get("certifications_items") or []),
        "volunteering": _dedupe_trimmed(profile.get("volunteering_items") or []),
        "skills": _dedupe_trimmed(profile.get("skills_items") or []),
        "honors": _dedupe_trimmed(profile.get("honors_items") or []),
        "languages": _dedupe_trimmed(profile.get("languages_items") or []),
        "featured_posts": _compact_posts(profile.get("featured_posts") or []),
        "activity_posts": _compact_posts(profile.get("activity_posts") or []),
        "recent_posts": _compact_posts(profile.get("recent_posts") or []),
        "errors": profile.get("errors") or [],
    }


def _default_output_paths(prefix: str) -> tuple[Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = f"{prefix}-{stamp}"
    return Path(f"{stem}.json"), Path(f"{stem}.csv")


def _resolve_collect_max_pages(args: argparse.Namespace) -> int:
    """Resolve collect max pages with person-query fast defaults.

    If caller does not pass --max-pages, person-query mode defaults to 1 page
    for faster turnaround. Other modes retain the historical default of 5 pages.
    """
    explicit = getattr(args, "max_pages", None)
    if explicit is not None:
        return explicit
    if bool(getattr(args, "person_query", False)) and bool(getattr(args, "query", "")):
        return 1
    return 5


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _records_to_csv_text(records: list[dict]) -> str:
    rows = [_flatten_csv_row(r) for r in records]
    fieldnames = [
        "run_id",
        "full_name",
        "linkedin_url",
        "profile_url",
        "source_url",
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
        "certifications_count",
        "certifications_preview",
        "volunteering_count",
        "volunteering_preview",
        "skills_count",
        "skills_preview",
        "honors_count",
        "honors_preview",
        "languages_count",
        "languages_preview",
        "featured_posts_count",
        "featured_posts_preview",
        "activity_posts_count",
        "activity_posts_preview",
        "recent_posts_count",
        "recent_posts_preview",
        "enrichment_errors",
        "collected_at",
    ]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return out.getvalue()


def _write_csv(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_records_to_csv_text(records), encoding="utf-8", newline="")


async def _collect_async(args: argparse.Namespace) -> int:
    from .auth.session_manager import SessionManager, SessionStatus
    from .models import SearchRequest
    from .profile_scraper import enrich_profile
    from .spiders.sales_nav import SalesNavigatorSpider
    from .spiders.search import LinkedInSearchSpider
    from .spiders.url_scraper import UrlSpider
    from .storage import LeadStore

    ok, message = validate_collect_mode(args)
    if not ok:
        print(message)
        return 2

    stdout_mode = bool(args.stdout)
    previous_disable_level = logging.root.manager.disable
    previous_debug_html_flag = os.environ.get("WS_PROSPECTOR_SAVE_DEBUG_HTML")
    if stdout_mode:
        # Keep stdout machine-readable for agent/tool callers.
        logging.disable(logging.INFO)
        if not args.debug_html:
            os.environ["WS_PROSPECTOR_SAVE_DEBUG_HTML"] = "0"
    mgr = SessionManager()
    status = await mgr.check_status()
    if status != SessionStatus.connected and args.login_if_needed:
        if not stdout_mode:
            print("Session not connected. Opening LinkedIn login...")
        status = await mgr.login()

    if status != SessionStatus.connected:
        print("LinkedIn session is not connected. Run `ws-prospector-debug status` or `--login-if-needed`.")
        return 2

    effective_max_pages = _resolve_collect_max_pages(args)

    if args.sales_url or args.url:
        input_url = args.sales_url or args.url
        spider = UrlSpider(mgr.user_data_dir, input_url, max_pages=effective_max_pages)
        source = spider._source.value
        query_text = summarize_url(input_url, source=source)
        person_query_mode = False
        run_params = {
            "mode": "url",
            "input_url": input_url,
            "max_pages": effective_max_pages,
            "max_leads": args.max_leads,
            "skip_enrich": args.skip_enrich,
        }
    else:
        person_query_mode = bool(args.person_query)
        req = SearchRequest(
            keywords=args.query or "",
            title=args.title or "",
            location=args.location or "",
            industry=args.industry or "",
            company=args.company or "",
            max_pages=effective_max_pages,
        )
        source = args.source
        if source == "sales_navigator":
            spider = SalesNavigatorSpider(mgr.user_data_dir, req, max_pages=effective_max_pages)
        else:
            spider = LinkedInSearchSpider(mgr.user_data_dir, req, max_pages=effective_max_pages)
        query_text = summarize_request(
            source=source,
            keywords=req.keywords,
            title=req.title,
            location=req.location,
            industry=req.industry,
            company=req.company,
        )
        input_url = None
        run_params = {
            "mode": "query",
            "source": source,
            "request": req.model_dump(mode="json"),
            "person_query_mode": person_query_mode,
            "max_pages": effective_max_pages,
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
        max_pages=effective_max_pages,
        params=run_params,
    )

    try:
        if not stdout_mode:
            print(f"Starting run #{run_id} ({source})")
            if person_query_mode and args.max_pages is None:
                print("  Person query mode: defaulting to --max-pages 1 for faster lookup.")

        async def on_progress(found: int, page: int) -> None:
            if not stdout_mode:
                print(f"  Search page {page}: {found} leads so far")

        leads = await spider.crawl(on_progress=on_progress)
        if args.max_leads and len(leads) > args.max_leads:
            leads = leads[: args.max_leads]
            if not stdout_mode:
                print(f"Trimmed to max leads: {args.max_leads}")

        if person_query_mode and leads:
            leads = sorted(
                leads,
                key=lambda lead: _person_match_score(args.query or "", getattr(lead, "full_name", None)),
                reverse=True,
            )[:1]
            if not stdout_mode:
                print("Person query mode enabled; selecting best-matching profile only.")

        if args.store and leads:
            store.upsert_many(leads)

        collected_at = datetime.now(timezone.utc).isoformat()
        records: list[dict] = []
        enriched_count = 0

        for idx, lead in enumerate(leads, 1):
            lead_dict = _lead_to_dict(lead)
            if not stdout_mode:
                print(f"  [{idx}/{len(leads)}] {lead.full_name}")
            if args.skip_enrich:
                profile_payload = {
                    "profile_url": lead.linkedin_url,
                    "summary": {},
                    "about": None,
                    "experience_items": [],
                    "education_items": [],
                    "certifications_items": [],
                    "volunteering_items": [],
                    "skills_items": [],
                    "honors_items": [],
                    "languages_items": [],
                    "featured_posts": [],
                    "activity_posts": [],
                    "recent_posts": [],
                    "errors": ["Skipped enrichment (remove --skip-enrich to enrich profiles)"],
                }
            elif args.max_enriched > 0 and idx > args.max_enriched:
                profile_payload = {
                    "profile_url": lead.linkedin_url,
                    "summary": {},
                    "about": None,
                    "experience_items": [],
                    "education_items": [],
                    "certifications_items": [],
                    "volunteering_items": [],
                    "skills_items": [],
                    "honors_items": [],
                    "languages_items": [],
                    "featured_posts": [],
                    "activity_posts": [],
                    "recent_posts": [],
                    "errors": [f"Skipped enrichment due --max-enriched={args.max_enriched}"],
                }
            else:
                profile_payload = await enrich_profile(
                    mgr.user_data_dir,
                    lead.linkedin_url,
                    full_name=lead.full_name,
                    current_company=lead.current_company,
                    location=lead.location,
                    max_posts=args.max_posts,
                    include_details=not args.fast,
                )
                if profile_payload.get("profile_url"):
                    enriched_count += 1

            record = {
                "run_id": run_id,
                "lead": lead_dict,
                "profile": profile_payload,
                "collected_at": collected_at,
            }
            records.append(record)
            if stdout_mode and args.stdout == "ndjson":
                out_record = _compact_record(record) if args.output_view == "compact" else record
                print(json.dumps(out_record, ensure_ascii=False), flush=True)

        json_out = Path(args.json_out) if args.json_out else None
        csv_out = Path(args.csv_out) if args.csv_out else None
        if not json_out and not csv_out and not stdout_mode:
            json_out, csv_out = _default_output_paths("lead-collection")

        if json_out:
            _write_json(json_out, records)
        if csv_out:
            _write_csv(csv_out, records)

        if stdout_mode:
            if args.stdout == "json":
                out_records = [_compact_record(r) for r in records] if args.output_view == "compact" else records
                print(json.dumps(out_records, ensure_ascii=False))
            elif args.stdout == "csv":
                print(_records_to_csv_text(records), end="")

        store.update_scrape_run(
            run_id,
            status="completed",
            leads_found=len(leads),
            leads_enriched=enriched_count,
            json_output_path=str(json_out) if json_out else None,
            csv_output_path=str(csv_out) if csv_out else None,
            params_json=run_params,
        )

        if not stdout_mode:
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
    finally:
        logging.disable(previous_disable_level)
        if previous_debug_html_flag is None:
            os.environ.pop("WS_PROSPECTOR_SAVE_DEBUG_HTML", None)
        else:
            os.environ["WS_PROSPECTOR_SAVE_DEBUG_HTML"] = previous_debug_html_flag


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
            "  ws-prospector-debug collect --query \"founder\" --source linkedin_search --max-pages 3\n"
            "  ws-prospector-debug collect --sales-url \"https://www.linkedin.com/sales/search/people?...\"\n"
            "  ws-prospector-debug collect --query \"head of partnerships\" --json-out out/leads.json --csv-out out/leads.csv\n\n"
            "Concurrency note:\n"
            "  - Run collect jobs sequentially per machine/session.\n"
            "  - Parallel collect runs share one Chromium user-data directory and can fail with profile lock errors.\n\n"
            "Agent-first (no files):\n"
            "  ws-prospector-debug collect --sales-url \"https://www.linkedin.com/sales/search/people?...\" --stdout json\n"
            "  ws-prospector-debug collect --query \"wealth advisor toronto\" --stdout json --fast\n\n"
            "Compact stdout (no jq reshape needed):\n"
            "  ws-prospector-debug collect --query \"Vriti Panwar\" --person-query --stdout json --output-view compact --fast\n\n"
            "Person query mode (explicit single-profile):\n"
            "  ws-prospector-debug collect --query \"Vriti Panwar\" --person-query --stdout json --fast\n\n"
            "Stream mode (low-latency for agents):\n"
            "  ws-prospector-debug collect --query \"Christo Mitov\" --max-leads 3 --max-enriched 1 --stdout ndjson --output-view compact --fast\n\n"
            "Output contract:\n"
            "  - JSON: array of records { run_id, lead, profile, collected_at }\n"
            "  - CSV: flattened columns for easy spreadsheet sharing\n"
            "  - NDJSON: one JSON record per line as each profile is processed\n"
            "  - output-view=compact (stdout JSON/NDJSON): flat, LLM-ready fields\n"
            "  - profile includes main-page sections when available:\n"
            "    experience_items, education_items, certifications_items,\n"
            "    volunteering_items, skills_items, honors_items, languages_items,\n"
            "    featured_posts, activity_posts, recent_posts"
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
        help=(
            "Search source for --query mode (default: linkedin_search). "
            "For Sales Navigator, prefer --sales-url."
        ),
    )
    collect.add_argument("--title", default="", help="Title filter (query mode).")
    collect.add_argument("--location", default="", help="Location filter (query mode).")
    collect.add_argument("--industry", default="", help="Industry filter (query mode, Sales Nav).")
    collect.add_argument("--company", default="", help="Company filter (query mode).")
    collect.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help=(
            "Max result pages to scrape (1-100). "
            "Default: 1 with --person-query, otherwise 5."
        ),
    )
    collect.add_argument("--max-leads", type=int, default=150, help="Hard cap on total leads processed.")
    collect.add_argument(
        "--person-query",
        action="store_true",
        help=(
            "Treat --query as a specific person lookup: select and enrich only the best-matching "
            "single profile from search results."
        ),
    )
    collect.add_argument(
        "--max-enriched",
        type=int,
        default=0,
        help=(
            "Optional cap on how many leads receive profile enrichment. "
            "0 means enrich all collected leads."
        ),
    )
    collect.add_argument("--max-posts", type=int, default=5, help="Max recent post snippets per profile.")
    collect.add_argument(
        "--fast",
        action="store_true",
        help=(
            "Fast mode: fetch only profile main page. Still parses top-level profile sections "
            "(experience/education/certifications/volunteering/skills/activity) without detail subpages."
        ),
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
    collect.add_argument(
        "--stdout",
        choices=["json", "csv", "ndjson"],
        default="",
        help=(
            "Write collected output to stdout instead of auto-writing files. "
            "When used, files are only written if --json-out/--csv-out are explicitly provided."
        ),
    )
    collect.add_argument(
        "--output-view",
        choices=["full", "compact"],
        default="full",
        help=(
            "Shape of stdout JSON/NDJSON payloads: full nested records or compact flat records. "
            "CSV output is unchanged."
        ),
    )
    collect.add_argument(
        "--debug-html",
        action="store_true",
        help=(
            "Keep writing debug HTML snapshots during collect runs. "
            "By default, stdout mode disables debug HTML writes for speed."
        ),
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
        if args.max_pages is not None:
            args.max_pages = max(1, min(int(args.max_pages), 100))
        args.max_leads = max(1, int(args.max_leads))
        args.max_enriched = max(0, int(args.max_enriched))
        args.max_posts = max(1, int(args.max_posts))
        args.store = not args.no_store
        raise SystemExit(asyncio.run(_collect_async(args)))

    parser.print_help()
