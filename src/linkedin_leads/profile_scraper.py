"""Profile enrichment helpers for CLI collection workflows."""

from __future__ import annotations

import asyncio
import logging
import re
import time as _time
from urllib.parse import unquote, urlparse

from scrapling.fetchers import StealthyFetcher

from .browser_lock import browser_lock
from .parsers.common import normalize_linkedin_url
from .parsers.profile_parser import (
    parse_about_text,
    parse_detail_list_items,
    parse_profile_summary,
    parse_recent_posts,
)

logger = logging.getLogger(__name__)


def _safe_visible_click(page: object, selector: str, *, max_clicks: int = 4) -> int:
    clicked = 0
    try:
        locator = page.locator(selector)
        total = min(locator.count(), max_clicks)
    except Exception:
        return 0

    for idx in range(total):
        try:
            btn = locator.nth(idx)
            if btn.is_visible(timeout=500):
                btn.click(timeout=1200)
                clicked += 1
                _time.sleep(0.2)
        except Exception:
            continue
    return clicked


def _profile_page_action(page: object) -> None:
    """Expand profile sections and load content before HTML capture."""
    try:
        page.evaluate("window.scrollTo(0, 260)")
        _time.sleep(0.4)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.55)")
        _time.sleep(0.7)
        page.evaluate("window.scrollTo(0, 0)")
        _time.sleep(0.3)

        selectors = [
            "button:has-text('Show more'):visible",
            "button:has-text('See more'):visible",
            "button:has-text('more'):visible",
            "a:has-text('Show all activity'):visible",
            "a:has-text('Show all experiences'):visible",
            "a:has-text('Show all education'):visible",
        ]
        for sel in selectors:
            _safe_visible_click(page, sel)
    except Exception:
        logger.debug("Profile page action failed", exc_info=True)


def _scroll_page_action(page: object) -> None:
    """Load dynamic list items on detail/activity pages."""
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.45)")
        _time.sleep(0.6)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.9)")
        _time.sleep(0.8)
        page.evaluate("window.scrollTo(0, 0)")
        _time.sleep(0.3)

        for sel in ["button:has-text('Show more'):visible", "button:has-text('See more'):visible"]:
            _safe_visible_click(page, sel)
    except Exception:
        logger.debug("Detail page action failed", exc_info=True)


def _fetch_page(user_data_dir: str, url: str, *, action: object | None = None) -> object | None:
    try:
        return StealthyFetcher.fetch(
            url,
            headless=True,
            real_chrome=True,
            user_data_dir=user_data_dir,
            block_images=True,
            disable_resources=False,
            page_action=action,
        )
    except Exception:
        logger.exception("Failed to fetch %s", url)
        return None


async def fetch_page(user_data_dir: str, url: str, *, action: object | None = None) -> object | None:
    async with browser_lock:
        return await asyncio.to_thread(_fetch_page, user_data_dir, url, action=action)


def _extract_profile_vanity(url: str) -> str | None:
    parsed = urlparse(url)
    path = unquote(parsed.path or "")
    match = re.search(r"/in/([^/?#]+)/?", path, flags=re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


async def resolve_profile_url(user_data_dir: str, raw_url: str | None) -> str | None:
    if not raw_url:
        return None

    normalized = normalize_linkedin_url(raw_url)
    if normalized and "/in/" in normalized:
        return normalized

    # Sales Nav URLs may still carry a readable vanity segment in their path.
    vanity = _extract_profile_vanity(raw_url)
    if vanity:
        return f"https://www.linkedin.com/in/{vanity}"

    if "/sales/" not in raw_url:
        return normalized

    page = await fetch_page(user_data_dir, raw_url, action=_scroll_page_action)
    if page is None:
        return None

    link_selectors = [
        "a[href*='/in/']",
        "a[data-anonymize='person-name'][href]",
    ]
    for selector in link_selectors:
        try:
            links = page.css(selector) or []
        except Exception:
            links = []
        for link in links:
            href = link.attrib.get("href") if hasattr(link, "attrib") else None
            candidate = normalize_linkedin_url(href)
            if candidate and "/in/" in candidate:
                return candidate

    return None


async def enrich_profile(
    user_data_dir: str,
    raw_url: str | None,
    *,
    max_posts: int = 5,
    include_details: bool = True,
) -> dict:
    """Resolve + fetch profile detail pages and parse a structured payload."""
    payload = {
        "profile_url": None,
        "summary": {},
        "about": None,
        "experience_items": [],
        "education_items": [],
        "recent_posts": [],
        "errors": [],
    }

    profile_url = await resolve_profile_url(user_data_dir, raw_url)
    payload["profile_url"] = profile_url
    if not profile_url:
        payload["errors"].append("Unable to resolve profile URL")
        return payload

    profile_page = await fetch_page(user_data_dir, profile_url, action=_profile_page_action)
    if profile_page is None:
        payload["errors"].append("Failed to fetch profile page")
        return payload

    payload["summary"] = parse_profile_summary(profile_page)
    payload["about"] = parse_about_text(profile_page)

    if not include_details:
        return payload

    base = profile_url.rstrip("/")
    exp_url = f"{base}/details/experience/"
    edu_url = f"{base}/details/education/"
    activity_url = f"{base}/recent-activity/all/"

    exp_page = await fetch_page(user_data_dir, exp_url, action=_scroll_page_action)
    if exp_page is None:
        payload["errors"].append("Failed to fetch experience details")
    else:
        payload["experience_items"] = parse_detail_list_items(exp_page, max_items=12)

    edu_page = await fetch_page(user_data_dir, edu_url, action=_scroll_page_action)
    if edu_page is None:
        payload["errors"].append("Failed to fetch education details")
    else:
        payload["education_items"] = parse_detail_list_items(edu_page, max_items=10)

    activity_page = await fetch_page(user_data_dir, activity_url, action=_scroll_page_action)
    if activity_page is None:
        payload["errors"].append("Failed to fetch recent activity")
    else:
        payload["recent_posts"] = parse_recent_posts(activity_page, max_items=max_posts)

    return payload
