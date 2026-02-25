"""Company Employees spider."""

from __future__ import annotations

from urllib.parse import quote_plus, urlencode

from ..config import DEFAULT_DELAY
from ..models import Lead, SearchRequest
from ..parsers.company_parser import parse_company_employees
from .base import LinkedInSpider


class CompanyEmployeesSpider(LinkedInSpider):
    download_delay: float = DEFAULT_DELAY

    def __init__(
        self,
        user_data_dir: str,
        request: SearchRequest,
        max_pages: int = 5,
    ) -> None:
        super().__init__(user_data_dir, max_pages=max_pages)
        self.request = request
        self._company_slug = request.company
        self._search_query = request.company

    def build_url(self, page: int) -> str:
        params: dict[str, str | int] = {"page": page}
        if self.request.keywords:
            params["keywords"] = self.request.keywords
        qs = urlencode(params, quote_via=quote_plus)
        slug = self._company_slug.strip("/").split("/")[-1]
        return f"https://www.linkedin.com/company/{slug}/people/?{qs}"

    def parse_page(self, page_response: object) -> list[Lead]:
        return parse_company_employees(
            page_response,
            company_name=self._company_slug,
            search_query=self._search_query,
        )
