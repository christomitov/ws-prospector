"""Parser for LinkedIn People Search result pages."""

from __future__ import annotations

import logging
import re

from ..models import Lead, LeadSource
from .common import (
    clean_text,
    extract_connection_degree,
    extract_mutual_count,
    normalize_linkedin_url,
    split_title_company,
)

logger = logging.getLogger(__name__)


def _css_first(el: object, selector: str) -> object | None:
    """Safe css_first that works on both Adaptor and Selector objects."""
    if hasattr(el, "css_first"):
        return el.css_first(selector)
    results = el.css(selector)
    return results[0] if results else None


def _full_text(el: object) -> str:
    """Get full text content of an element, including text inside child tags.

    Scrapling's Selector.text only returns direct text, and get_all_text()
    misses some children. Stripping HTML tags from html_content gives us
    the complete flattened text.
    """
    import html as html_mod

    if hasattr(el, "html_content"):
        raw = el.html_content
        if isinstance(raw, str):
            return html_mod.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
    if hasattr(el, "get_all_text"):
        return el.get_all_text().strip()
    return (el.text or "").strip()


def parse_search_results(page: object, search_query: str = "") -> list[Lead]:
    """Extract leads from a LinkedIn People Search results page."""
    leads: list[Lead] = []

    cards = _find_result_cards(page)
    if not cards:
        profile_links = page.css("a[href*='/in/']") or []
        if profile_links:
            logger.warning(
                "No result cards found on search page (%d profile links present).",
                len(profile_links),
            )
        else:
            logger.info("No result cards found on search page (0 profile links; likely end of results).")
        return leads

    logger.info("Found %d result cards", len(cards))
    for card in cards:
        try:
            lead = _parse_card(card, search_query)
            if lead:
                leads.append(lead)
            else:
                logger.debug("Card skipped — could not extract name")
        except Exception:
            logger.debug("Failed to parse a search result card", exc_info=True)

    return leads


def _find_result_cards(page: object) -> list:
    """Try multiple selectors to find result cards."""
    strategies = [
        ("div[data-view-name='people-search-result']", "data-view-name"),
        ("li.reusable-search__result-container", "legacy specific class"),
        ("div[class*='entity-result']", "legacy entity-result"),
        ("div[role='list'] > div", "role=list > div"),
    ]
    for selector, name in strategies:
        cards = page.css(selector)
        if cards:
            logger.info("Matched %d cards via: %s", len(cards), name)
            return list(cards)
        logger.debug("Strategy '%s' matched 0", name)

    all_links = page.css("a[href*='/in/']")
    if all_links:
        logger.warning(
            "No card strategy matched. Page has %d profile links total.",
            len(all_links),
        )
    else:
        logger.info("No card strategy matched. Page has 0 profile links total (likely end of results).")
    return []


def _parse_card(card: object, search_query: str) -> Lead | None:
    """Parse a single search result card into a Lead."""
    # ── Name + profile URL ──
    title_link = _css_first(card, "a[data-view-name='search-result-lockup-title']")
    profile_link = _css_first(card, "a[href*='/in/']")

    full_name = clean_text(title_link.text if title_link else None)
    if not full_name:
        avatar = _css_first(card, "figure[aria-label]")
        full_name = clean_text(avatar.attrib.get("aria-label") if avatar else None)
    if not full_name:
        full_name = clean_text(profile_link.text if profile_link else None)
    if not full_name:
        return None

    linkedin_url = normalize_linkedin_url(
        (profile_link or title_link).attrib.get("href") if (profile_link or title_link) else None
    )

    # ── Connection degree from spans like "• 2nd" ──
    connection_degree = None
    spans = card.css("span") or []
    for span in spans:
        txt = span.text.strip() if span.text else ""
        if re.search(r"•\s*\d+(?:st|nd|rd|th)", txt):
            connection_degree = extract_connection_degree(txt)
            break

    # ── Extract text from each <p>, using _full_text to capture child elements ──
    # Typical <p> sequence:
    #   p[0]: name + degree badge (child elements)
    #   p[1]: headline
    #   p[2]: location
    #   p[3]: "Current: Title at Company"
    #   p[4+]: social proof / mutual connections
    headline = None
    location = None
    current_title = None
    current_company = None
    mutual_connections = None

    p_elements = card.css("p") or []
    content_ps: list[str] = []

    for p in p_elements:
        txt = clean_text(_full_text(p))
        if not txt:
            continue

        if txt.startswith("Current:"):
            current_info = clean_text(txt.replace("Current:", "").strip())
            if current_info:
                current_title, current_company = split_title_company(current_info)
        elif "mutual connection" in txt.lower():
            mutual_connections = extract_mutual_count(txt)
        elif full_name not in txt and "Connect" != txt:
            content_ps.append(txt)

    if len(content_ps) >= 1:
        headline = content_ps[0]
    if len(content_ps) >= 2:
        location = content_ps[1]

    if not current_title and headline:
        current_title, current_company = split_title_company(headline)

    return Lead(
        linkedin_url=linkedin_url,
        full_name=full_name,
        headline=headline,
        current_title=current_title,
        current_company=current_company,
        location=location,
        connection_degree=connection_degree,
        mutual_connections=mutual_connections,
        source=LeadSource.linkedin_search,
        search_query=search_query,
    )
