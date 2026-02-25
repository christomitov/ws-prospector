"""CLI debug tool for inspecting scrape results without the web UI.

Usage:
    uv run ws-prospector-debug status          # Check session status
    uv run ws-prospector-debug html [N]        # Print summary of debug HTML page N (default 1)
    uv run ws-prospector-debug parse [N]       # Attempt to parse debug HTML page N and show results
    uv run ws-prospector-debug search "query"  # Run a one-off search and print results to stdout
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys

from .config import DATA_DIR, ensure_dirs

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEBUG_HTML_DIR = DATA_DIR / "debug_html"


def cmd_status():
    from .auth.session_manager import SessionManager

    mgr = SessionManager()
    status = asyncio.run(mgr.check_status())
    print(f"Session: {status.value}")


def cmd_html(page_num: int = 1):
    path = DEBUG_HTML_DIR / f"page_{page_num}.html"
    if not path.exists():
        print(f"No debug HTML at {path}. Run a search first.")
        return

    content = path.read_text(encoding="utf-8")
    print(f"File: {path}")
    print(f"Size: {len(content):,} bytes")

    # Count key elements
    cards = len(re.findall(r'data-view-name="people-search-result"', content))
    links = len(re.findall(r'href="https://www.linkedin.com/in/[^"]+', content))
    titles = len(re.findall(r'data-view-name="search-result-lockup-title"', content))
    print(f"Result cards (data-view-name): {cards}")
    print(f"Profile links: {links}")
    print(f"Title elements: {titles}")

    # Extract visible text from each card
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


def cmd_parse(page_num: int = 1):
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


def cmd_search(query: str):
    from .auth.session_manager import SessionManager
    from .models import SearchRequest
    from .spiders.search import LinkedInSearchSpider
    from .storage import LeadStore

    mgr = SessionManager()
    req = SearchRequest(keywords=query, max_pages=1)
    spider = LinkedInSearchSpider(mgr.user_data_dir, req, max_pages=1)

    async def run():
        async def on_progress(found, page):
            print(f"  Page {page}: {found} leads so far...")

        return await spider.crawl(on_progress=on_progress)

    print(f"Searching for: {query}")
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


def main():
    ensure_dirs()
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    cmd = args[0]
    if cmd == "status":
        cmd_status()
    elif cmd == "html":
        cmd_html(int(args[1]) if len(args) > 1 else 1)
    elif cmd == "parse":
        cmd_parse(int(args[1]) if len(args) > 1 else 1)
    elif cmd == "search":
        if len(args) < 2:
            print("Usage: ws-prospector-debug search 'query'")
            return
        cmd_search(args[1])
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
