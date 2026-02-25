"""Direct URL scraper — paste any LinkedIn/Sales Navigator URL and scrape all pages."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from ..config import DEFAULT_DELAY, SALES_NAV_DELAY
from ..models import Lead, LeadSource
from ..parsers.navigator_parser import parse_navigator_results
from ..parsers.search_parser import parse_search_results
from ..parsers.company_parser import parse_company_employees
from .base import LinkedInSpider


_VOLATILE_QUERY_PARAMS = {"page", "sessionId", "_ntb", "viewAllFilters"}


def detect_source(url: str) -> LeadSource:
    """Detect the lead source type from a URL."""
    if "/sales/" in url:
        return LeadSource.sales_navigator
    if "/company/" in url and "/people" in url:
        return LeadSource.company_employees
    return LeadSource.linkedin_search


def canonicalize_search_query(url: str) -> str:
    """Drop volatile URL params so repeated runs can be tracked as one search."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    for key in _VOLATILE_QUERY_PARAMS:
        qs.pop(key, None)
    query = urlencode(qs, doseq=True)
    return urlunparse(parsed._replace(query=query))


class UrlSpider(LinkedInSpider):
    """Spider that scrapes a user-provided URL, paginating through all pages."""

    def __init__(self, user_data_dir: str, url: str, max_pages: int = 5) -> None:
        self._source = detect_source(url)
        delay = SALES_NAV_DELAY if self._source == LeadSource.sales_navigator else DEFAULT_DELAY
        super().__init__(user_data_dir, max_pages=max_pages)
        self.download_delay = delay
        self._base_url = url
        self._search_query = canonicalize_search_query(url)
        self._parsed = urlparse(url)

    def build_url(self, page: int) -> str:
        """Replace or insert the page parameter in the URL."""
        qs = parse_qs(self._parsed.query, keep_blank_values=True)
        qs["page"] = [str(page)]
        new_query = urlencode(qs, doseq=True)
        return urlunparse(self._parsed._replace(query=new_query))

    def parse_page(self, page_response: object) -> list[Lead]:
        query_str = self._search_query
        if self._source == LeadSource.sales_navigator:
            return parse_navigator_results(page_response, search_query=query_str)
        if self._source == LeadSource.company_employees:
            # Try to extract company name from URL
            m = re.search(r"/company/([^/]+)", self._base_url)
            company = m.group(1) if m else ""
            return parse_company_employees(page_response, company_name=company, search_query=query_str)
        return parse_search_results(page_response, search_query=query_str)
