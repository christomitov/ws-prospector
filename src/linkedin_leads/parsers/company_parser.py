"""Parser for Company Employees pages."""

from __future__ import annotations

import logging

from ..models import Lead, LeadSource
from .common import (
    clean_text,
    extract_connection_degree,
    normalize_linkedin_url,
    split_title_company,
)

logger = logging.getLogger(__name__)


def parse_company_employees(page: object, company_name: str = "", search_query: str = "") -> list[Lead]:
    """Extract leads from a Company People page."""
    leads: list[Lead] = []

    cards = _find_result_cards(page)
    if not cards:
        logger.debug("No employee cards found on company page")
        return leads

    for card in cards:
        try:
            lead = _parse_card(card, company_name, search_query)
            if lead:
                leads.append(lead)
        except Exception:
            logger.debug("Failed to parse a company employee card", exc_info=True)

    return leads


def _find_result_cards(page: object) -> list:
    """Try multiple selectors for company employee cards."""
    # Strategy 1: org-people card
    cards = page.css("li.org-people-profile-card__profile-card-spacing")
    if cards:
        return cards

    # Strategy 2: partial class
    cards = page.css("div[class*='org-people-profile-card']")
    if cards:
        return cards

    # Strategy 3: reusable search results (company people tab uses search-like layout)
    cards = page.css("li.reusable-search__result-container")
    if cards:
        return cards

    # Strategy 4: structural
    cards = page.css("div[class*='org-people'] li")
    if cards:
        return cards

    return []


def _parse_card(card: object, company_name: str, search_query: str) -> Lead | None:
    """Parse a single company employee card into a Lead."""
    # Name + profile link
    link_el = (
        card.css_first("a.app-aware-link[href*='/in/']")
        or card.css_first("a[href*='/in/']")
    )

    name_el = (
        card.css_first("div.org-people-profile-card__profile-title")
        or card.css_first("div[class*='profile-card__profile-title']")
        or card.css_first("span[dir='ltr']")
    )

    full_name = clean_text(name_el.text if name_el else (link_el.text if link_el else None))
    if not full_name:
        return None

    linkedin_url = normalize_linkedin_url(
        link_el.attrib.get("href") if link_el else None
    )

    # Subtitle / headline
    subtitle_el = (
        card.css_first("div.org-people-profile-card__subtitle")
        or card.css_first("div[class*='profile-card__subtitle']")
    )
    headline = clean_text(subtitle_el.text if subtitle_el else None)

    title, parsed_company = split_title_company(headline)

    # Location
    location_el = (
        card.css_first("div.org-people-profile-card__location")
        or card.css_first("div[class*='profile-card__location']")
    )
    location = clean_text(location_el.text if location_el else None)

    # Connection degree
    degree_el = card.css_first("span[class*='badge']")
    connection_degree = extract_connection_degree(
        degree_el.text if degree_el else None
    )

    return Lead(
        linkedin_url=linkedin_url,
        full_name=full_name,
        headline=headline,
        current_title=title,
        current_company=parsed_company or company_name,
        location=location,
        connection_degree=connection_degree,
        mutual_connections=None,
        source=LeadSource.company_employees,
        search_query=search_query,
    )
