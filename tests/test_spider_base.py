"""Tests for base spider fetch heuristics."""

from linkedin_leads.spiders.base import LinkedInSpider


class _DummyResponse:
    def __init__(self, html_content: str):
        self.html_content = html_content


class _DummySpider(LinkedInSpider):
    def build_url(self, page: int) -> str:
        return "https://example.com"

    def parse_page(self, page_response: object) -> list:
        return []


def test_should_retry_headful_for_sales_loader_only_html():
    spider = _DummySpider(user_data_dir="/tmp")
    response = _DummyResponse("<div class='initial-load-animation'><div class='salesnav-image'></div></div>")
    assert spider._should_retry_headful(response, "https://www.linkedin.com/sales/search/people?page=1")


def test_should_not_retry_headful_when_sales_leads_present():
    spider = _DummySpider(user_data_dir="/tmp")
    response = _DummyResponse("<a href='/sales/lead/ACwAAAA'></a>")
    assert not spider._should_retry_headful(response, "https://www.linkedin.com/sales/search/people?page=1")


def test_should_not_retry_headful_for_non_sales_urls():
    spider = _DummySpider(user_data_dir="/tmp")
    response = _DummyResponse("<div class='initial-load-animation'></div>")
    assert not spider._should_retry_headful(response, "https://www.linkedin.com/search/results/people/?page=1")
