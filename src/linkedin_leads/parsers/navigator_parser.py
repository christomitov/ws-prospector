"""Parser for Sales Navigator search result pages."""

from __future__ import annotations

import logging

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


def parse_navigator_results(page: object, search_query: str = "") -> list[Lead]:
    """Extract leads from a Sales Navigator People Search results page."""
    leads: list[Lead] = []

    cards = _find_result_cards(page)
    if not cards:
        logger.debug("No result cards found on Sales Navigator page")
        return leads

    for card in cards:
        try:
            lead = _parse_card(card, search_query)
            if lead:
                leads.append(lead)
        except Exception:
            logger.debug("Failed to parse a Sales Nav result card", exc_info=True)

    return leads


def _find_result_cards(page: object) -> list:
    """Try multiple selectors for Sales Navigator result cards."""
    # Strategy 1: Modern Sales Nav result container.
    cards = page.css("div[data-x-search-result='LEAD']")
    if cards:
        return cards

    # Strategy 2: Sales Nav list rows.
    cards = page.css("li[class*='artdeco-list__item']")
    if cards:
        return cards

    # Strategy 3: legacy result list items.
    cards = page.css("ol.search-results__result-list > li")
    if cards:
        return cards

    # Strategy 4: broad search
    cards = page.css("div[class*='search-results'] li[class*='result']")
    if cards:
        return cards

    return []


def _parse_card(card: object, search_query: str) -> Lead | None:
    """Parse a single Sales Navigator result card into a Lead."""
    # Name + profile link
    link_el = (
        _css_first(card, "a[data-lead-search-result*='profile-link']")
        or _css_first(card, "a[href*='/sales/lead/']")
        or _css_first(card, "a[href*='/sales/people/']")
        or _css_first(card, "a[data-anonymize='person-name']")
    )

    name_el = (
        _css_first(card, "span[data-anonymize='person-name']")
        or _css_first(card, "a[data-anonymize='person-name']")
    )

    full_name = clean_text(name_el.text if name_el else (link_el.text if link_el else None))
    if not full_name:
        return None

    # Sales Navigator uses /sales/lead/ URLs — normalize to standard /in/ if possible
    raw_url = link_el.attrib.get("href") if link_el else None
    linkedin_url = normalize_linkedin_url(raw_url)

    # Title
    title_el = (
        _css_first(card, "span[data-anonymize='title']")
        or _css_first(card, "span[class*='result-lockup__highlight-keyword']")
    )
    current_title = clean_text(title_el.text if title_el else None)

    # Company
    company_el = (
        _css_first(card, "a[data-anonymize='company-name']")
        or _css_first(card, "span[data-anonymize='company-name']")
    )
    current_company = clean_text(company_el.text if company_el else None)

    # Headline fallback
    headline = f"{current_title} at {current_company}" if current_title and current_company else current_title

    # Location
    location_el = (
        _css_first(card, "span[data-anonymize='location']")
        or _css_first(card, "span[class*='result-lockup__misc-item']")
    )
    location = clean_text(location_el.text if location_el else None)

    # Connection degree
    degree_el = (
        _css_first(card, "span.artdeco-entity-lockup__degree")
        or _css_first(card, "span[class*='result-lockup__badge']")
    )
    connection_degree = extract_connection_degree(
        degree_el.text if degree_el else None
    )

    # Mutual connections
    mutual_el = _css_first(card, "button[class*='result-lockup__common-connections']")
    mutual_connections = extract_mutual_count(mutual_el.text if mutual_el else None)
    if mutual_connections is None:
        for el in card.css("button, span"):
            txt = clean_text(el.text if hasattr(el, "text") else None)
            if not txt or "mutual connection" not in txt.lower():
                continue
            mutual_connections = extract_mutual_count(txt)
            if mutual_connections is not None:
                break

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
        source=LeadSource.sales_navigator,
        search_query=search_query,
    )
