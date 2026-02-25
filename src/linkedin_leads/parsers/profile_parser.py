"""Best-effort parsing of LinkedIn profile pages and detail subpages."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .common import clean_text


def _css_first(el: object, selector: str) -> object | None:
    try:
        if hasattr(el, "css_first"):
            return el.css_first(selector)
        results = el.css(selector)
        return results[0] if results else None
    except Exception:
        return None


def _full_text(el: object) -> str:
    if hasattr(el, "get_all_text"):
        return clean_text(el.get_all_text()) or ""
    if hasattr(el, "text"):
        return clean_text(el.text) or ""
    return ""


def _abs_linkedin_url(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip()
    if value.startswith("//"):
        value = f"https:{value}"
    elif value.startswith("/"):
        value = f"https://www.linkedin.com{value}"
    elif value.startswith("www.linkedin.com"):
        value = f"https://{value}"

    parsed = urlparse(value)
    if parsed.netloc and "linkedin.com" in parsed.netloc:
        return value.split("?")[0]
    return None


def parse_profile_summary(page: object) -> dict:
    """Extract top-of-profile summary fields."""
    name = None
    headline = None
    location = None

    name_el = _css_first(page, "h1")
    if name_el:
        name = clean_text(name_el.text)

    headline_selectors = [
        "main section div.text-body-medium",
        "main div.ph5 div.text-body-medium",
        "section div.text-body-medium",
    ]
    for selector in headline_selectors:
        el = _css_first(page, selector)
        text = clean_text(el.text if el else None)
        if text:
            headline = text
            break

    location_selectors = [
        "main section span.text-body-small.inline.t-black--light.break-words",
        "main div.ph5 span.text-body-small",
        "section span.text-body-small",
    ]
    for selector in location_selectors:
        el = _css_first(page, selector)
        text = clean_text(el.text if el else None)
        if text:
            location = text
            break

    return {
        "name": name,
        "headline": headline,
        "location": location,
    }


def parse_about_text(page: object, *, max_chars: int = 4000) -> str | None:
    """Extract profile About section text."""
    candidate_selectors = [
        "section:has(#about) div.inline-show-more-text",
        "section:has(#about) div[dir='ltr']",
        "section:has(#about) span[aria-hidden='true']",
    ]
    for selector in candidate_selectors:
        el = _css_first(page, selector)
        if not el:
            continue
        text = _full_text(el)
        if text and len(text) > 20:
            return text[:max_chars]

    # Fallback: inspect section blocks and pick one that looks like About.
    sections = page.css("main section") or page.css("section") or []
    for section in sections:
        txt = _full_text(section)
        if not txt or len(txt) < 25:
            continue
        lower = txt.lower()
        if not lower.startswith("about") and "\nabout" not in lower and " about " not in lower[:120]:
            continue
        cleaned = re.sub(r"^about\s*", "", txt, flags=re.IGNORECASE).strip()
        if cleaned:
            return cleaned[:max_chars]

    return None


def parse_detail_list_items(page: object, *, max_items: int = 12) -> list[str]:
    """Extract normalized list rows from details pages (experience/education)."""
    selectors = [
        "li.pvs-list__paged-list-item",
        "main li.artdeco-list__item",
        "main li",
    ]

    rows: list[str] = []
    seen: set[str] = set()

    def _push(text: str) -> None:
        text = clean_text(text) or ""
        if not text:
            return
        lower = text.lower()
        if lower.startswith(("show all", "see all", "add profile section")):
            return
        if len(text) < 18:
            return
        if text in seen:
            return
        seen.add(text)
        rows.append(text)

    for selector in selectors:
        items = page.css(selector) or []
        if not items:
            continue
        for item in items:
            _push(_full_text(item))
            if len(rows) >= max_items:
                return rows

    return rows[:max_items]


def parse_recent_posts(page: object, *, max_items: int = 5) -> list[dict]:
    """Extract recent post snippets from activity page."""
    results: list[dict] = []
    seen_urls: set[str] = set()

    card_selectors = [
        "div.feed-shared-update-v2",
        "article",
        "main li",
    ]

    def _append(url: str | None, text: str | None) -> None:
        if len(results) >= max_items:
            return
        clean = clean_text(text)
        if not clean or len(clean) < 20:
            return
        abs_url = _abs_linkedin_url(url)
        if abs_url and abs_url in seen_urls:
            return
        if abs_url:
            seen_urls.add(abs_url)
        results.append({"url": abs_url, "text": clean[:1200]})

    for selector in card_selectors:
        cards = page.css(selector) or []
        for card in cards:
            link = _css_first(card, "a[href*='/feed/update/']") or _css_first(card, "a[href*='/posts/']")
            href = link.attrib.get("href") if link and hasattr(link, "attrib") else None
            _append(href, _full_text(card))
            if len(results) >= max_items:
                return results

    # Fallback: no post cards found, still expose raw update links.
    links = page.css("a[href*='/feed/update/'], a[href*='/posts/']") or []
    for link in links:
        href = link.attrib.get("href") if hasattr(link, "attrib") else None
        text = _full_text(link)
        _append(href, text)
        if len(results) >= max_items:
            break

    return results
