"""LinkedIn People Search spider."""

from __future__ import annotations

from urllib.parse import quote_plus, urlencode

from ..config import DEFAULT_DELAY
from ..models import Lead, SearchRequest
from ..parsers.search_parser import parse_search_results
from .base import LinkedInSpider


class LinkedInSearchSpider(LinkedInSpider):
    download_delay: float = DEFAULT_DELAY

    def __init__(
        self,
        user_data_dir: str,
        request: SearchRequest,
        max_pages: int = 5,
    ) -> None:
        super().__init__(user_data_dir, max_pages=max_pages)
        self.request = request
        self._search_query = request.keywords

    def build_url(self, page: int) -> str:
        params: dict[str, str | int] = {"page": page}
        if self.request.keywords:
            params["keywords"] = self.request.keywords
        if self.request.title:
            params["titleFreeText"] = self.request.title
        if self.request.location:
            params["geoUrn"] = self.request.location
        if self.request.company:
            params["company"] = self.request.company
        qs = urlencode(params, quote_via=quote_plus)
        return f"https://www.linkedin.com/search/results/people/?{qs}"

    def parse_page(self, page_response: object) -> list[Lead]:
        return parse_search_results(page_response, self._search_query)
