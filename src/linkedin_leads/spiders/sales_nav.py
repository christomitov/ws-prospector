"""Sales Navigator People Search spider."""

from __future__ import annotations

from urllib.parse import quote_plus, urlencode

from ..config import SALES_NAV_DELAY
from ..models import Lead, SearchRequest
from ..parsers.navigator_parser import parse_navigator_results
from .base import LinkedInSpider


class SalesNavigatorSpider(LinkedInSpider):
    download_delay: float = SALES_NAV_DELAY

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
            params["query"] = self.request.keywords
        if self.request.title:
            params["titleIncluded"] = self.request.title
        if self.request.location:
            params["geoIncluded"] = self.request.location
        if self.request.company:
            params["currentCompany"] = self.request.company
        if self.request.industry:
            params["industryIncluded"] = self.request.industry
        qs = urlencode(params, quote_via=quote_plus)
        return f"https://www.linkedin.com/sales/search/people?{qs}"

    def parse_page(self, page_response: object) -> list[Lead]:
        return parse_navigator_results(page_response, self._search_query)
