"""Tests for URL scraping helpers."""

from linkedin_leads.models import LeadSource
from linkedin_leads.spiders.url_scraper import canonicalize_search_query, detect_source


def test_detect_source_sales_nav():
    assert detect_source("https://www.linkedin.com/sales/search/people?query=(keywords:board)") == LeadSource.sales_navigator


def test_detect_source_company_people():
    assert detect_source("https://www.linkedin.com/company/acme/people/") == LeadSource.company_employees


def test_detect_source_regular_search_default():
    assert detect_source("https://www.linkedin.com/search/results/people/?keywords=board") == LeadSource.linkedin_search


def test_canonicalize_search_query_removes_volatile_params():
    url = (
        "https://www.linkedin.com/sales/search/people?"
        "query=(keywords:board)&sessionId=abc&page=3&viewAllFilters=true&_ntb=def"
    )
    canonical = canonicalize_search_query(url)
    assert "sessionId=" not in canonical
    assert "page=" not in canonical
    assert "viewAllFilters=" not in canonical
    assert "_ntb=" not in canonical
    assert "query=%28keywords%3Aboard%29" in canonical
