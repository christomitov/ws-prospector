"""Profile enrichment helpers for CLI collection workflows."""

from __future__ import annotations

import asyncio
import logging
import re
import time as _time
from urllib.parse import quote_plus, unquote, urlparse

from scrapling.fetchers import StealthyFetcher

from .browser_lock import browser_lock
from .parsers.common import normalize_linkedin_url
from .parsers.profile_parser import (
    parse_about_text,
    parse_activity_posts,
    parse_detail_list_items,
    parse_featured_posts,
    parse_profile_section_items,
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


def _normalize_token(text: str | None) -> str:
    value = (text or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _name_similarity_score(expected: str | None, actual: str | None) -> int:
    left = _normalize_token(expected)
    right = _normalize_token(actual)
    if not left or not right:
        return 0
    if left == right:
        return 40
    left_parts = left.split()
    right_parts = right.split()
    overlap = len(set(left_parts).intersection(right_parts))
    if overlap:
        return min(25, overlap * 10)
    if left in right or right in left:
        return 10
    return 0


def _company_similarity_score(expected: str | None, actual: str | None) -> int:
    left = _normalize_token(expected)
    right = _normalize_token(actual)
    if not left or not right:
        return 0
    if left == right:
        return 20
    if left in right or right in left:
        return 12
    overlap = len(set(left.split()).intersection(right.split()))
    return min(8, overlap * 4)


def _location_similarity_score(expected: str | None, actual: str | None) -> int:
    left = _normalize_token(expected)
    right = _normalize_token(actual)
    if not left or not right:
        return 0
    if left == right:
        return 8
    city = left.split(",")[0].strip() if "," in left else left.split(" ")[0]
    if city and city in right:
        return 6
    return 0


def _lead_match_score(
    lead: object,
    *,
    full_name: str | None,
    current_company: str | None,
    location: str | None,
) -> int:
    score = 0
    score += _name_similarity_score(full_name, getattr(lead, "full_name", None))
    score += _company_similarity_score(current_company, getattr(lead, "current_company", None))
    score += _location_similarity_score(location, getattr(lead, "location", None))

    profile_url = getattr(lead, "linkedin_url", None) or ""
    if "/in/" in profile_url:
        score += 10
    return score


async def _resolve_profile_url_via_people_search(
    user_data_dir: str,
    *,
    full_name: str | None,
    current_company: str | None,
    location: str | None,
) -> str | None:
    from .parsers.search_parser import parse_search_results

    if not full_name:
        return None

    name_clean = re.sub(r"\([^)]*\)", "", full_name).strip()
    candidate_queries = [
        " ".join(v for v in [full_name.strip(), current_company or "", location or ""] if v),
        " ".join(v for v in [name_clean, current_company or "", location or ""] if v),
        " ".join(v for v in [full_name.strip(), current_company or ""] if v),
        " ".join(v for v in [name_clean, current_company or ""] if v),
        " ".join(v for v in [full_name.strip(), location or ""] if v),
        " ".join(v for v in [name_clean, location or ""] if v),
        full_name.strip(),
        name_clean,
    ]

    seen_queries: set[str] = set()
    for query in candidate_queries:
        query = query.strip()
        if not query or query in seen_queries:
            continue
        seen_queries.add(query)

        search_url = f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(query)}"
        page = await fetch_page(user_data_dir, search_url, action=_scroll_page_action)
        if page is None:
            continue

        candidates = parse_search_results(page, search_query=query)
        if not candidates:
            continue

        ranked = sorted(
            candidates,
            key=lambda lead: _lead_match_score(
                lead,
                full_name=full_name,
                current_company=current_company,
                location=location,
            ),
            reverse=True,
        )
        best = ranked[0]
        best_url = getattr(best, "linkedin_url", None)
        if best_url and "/in/" in best_url:
            return best_url

    return None


async def resolve_profile_url(
    user_data_dir: str,
    raw_url: str | None,
    *,
    full_name: str | None = None,
    current_company: str | None = None,
    location: str | None = None,
) -> str | None:
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
        if normalized and "/in/" in normalized:
            return normalized
        return await _resolve_profile_url_via_people_search(
            user_data_dir,
            full_name=full_name,
            current_company=current_company,
            location=location,
        )

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

    return await _resolve_profile_url_via_people_search(
        user_data_dir,
        full_name=full_name,
        current_company=current_company,
        location=location,
    )


async def enrich_profile(
    user_data_dir: str,
    raw_url: str | None,
    *,
    full_name: str | None = None,
    current_company: str | None = None,
    location: str | None = None,
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
        "certifications_items": [],
        "volunteering_items": [],
        "skills_items": [],
        "honors_items": [],
        "languages_items": [],
        "featured_posts": [],
        "activity_posts": [],
        "recent_posts": [],
        "errors": [],
    }

    profile_url = await resolve_profile_url(
        user_data_dir,
        raw_url,
        full_name=full_name,
        current_company=current_company,
        location=location,
    )
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
    payload["experience_items"] = parse_profile_section_items(
        profile_page, section_hint="experience", max_items=12
    )
    payload["education_items"] = parse_profile_section_items(
        profile_page, section_hint="education", max_items=10
    )
    payload["certifications_items"] = parse_profile_section_items(
        profile_page, section_hint="certifications", max_items=12
    )
    payload["volunteering_items"] = parse_profile_section_items(
        profile_page, section_hint="volunteering", max_items=10
    )
    payload["skills_items"] = parse_profile_section_items(
        profile_page, section_hint="skills", max_items=20
    )
    payload["honors_items"] = parse_profile_section_items(
        profile_page, section_hint="honors", max_items=10
    )
    payload["languages_items"] = parse_profile_section_items(
        profile_page, section_hint="languages", max_items=10
    )
    payload["featured_posts"] = parse_featured_posts(profile_page, max_items=max_posts)
    payload["activity_posts"] = parse_activity_posts(profile_page, max_items=max_posts)

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
        detail_experience = parse_detail_list_items(
            exp_page, max_items=12, section_hint="experience"
        )
        if detail_experience:
            payload["experience_items"] = detail_experience

    edu_page = await fetch_page(user_data_dir, edu_url, action=_scroll_page_action)
    if edu_page is None:
        payload["errors"].append("Failed to fetch education details")
    else:
        detail_education = parse_detail_list_items(
            edu_page, max_items=10, section_hint="education"
        )
        if detail_education:
            payload["education_items"] = detail_education

    activity_page = await fetch_page(user_data_dir, activity_url, action=_scroll_page_action)
    if activity_page is None:
        payload["errors"].append("Failed to fetch recent activity")
    else:
        payload["recent_posts"] = parse_recent_posts(activity_page, max_items=max_posts)

    return payload
