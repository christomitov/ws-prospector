from __future__ import annotations

import asyncio

from linkedin_leads.models import Lead, LeadSource
from linkedin_leads.profile_scraper import _lead_match_score, resolve_profile_url


def _lead(name: str, url: str, company: str, location: str) -> Lead:
    return Lead(
        linkedin_url=url,
        full_name=name,
        headline=None,
        current_title=None,
        current_company=company,
        location=location,
        source=LeadSource.linkedin_search,
    )


def test_lead_match_score_prefers_exact_name_company_location() -> None:
    exact = _lead(
        "James Castle",
        "https://www.linkedin.com/in/jamescastleca",
        "Cyber Security Global Alliance",
        "Toronto, Ontario, Canada",
    )
    weak = _lead(
        "James C",
        "https://www.linkedin.com/in/james-c",
        "Other Company",
        "Vancouver, British Columbia, Canada",
    )

    exact_score = _lead_match_score(
        exact,
        full_name="James Castle",
        current_company="Cyber Security Global Alliance",
        location="Toronto, Ontario, Canada",
    )
    weak_score = _lead_match_score(
        weak,
        full_name="James Castle",
        current_company="Cyber Security Global Alliance",
        location="Toronto, Ontario, Canada",
    )

    assert exact_score > weak_score


def test_resolve_profile_url_falls_back_to_people_search(monkeypatch: object) -> None:
    class EmptyPage:
        def css(self, selector: str) -> list:
            return []

    async def fake_fetch_page(user_data_dir: str, raw_url: str, *, action: object | None = None) -> object:
        return EmptyPage()

    calls: dict[str, str | None] = {}

    async def fake_people_search(
        user_data_dir: str,
        *,
        full_name: str | None,
        current_company: str | None,
        location: str | None,
    ) -> str | None:
        calls["full_name"] = full_name
        calls["current_company"] = current_company
        calls["location"] = location
        return "https://www.linkedin.com/in/jamescastleca"

    monkeypatch.setattr("linkedin_leads.profile_scraper.fetch_page", fake_fetch_page)
    monkeypatch.setattr(
        "linkedin_leads.profile_scraper._resolve_profile_url_via_people_search",
        fake_people_search,
    )

    result = asyncio.run(
        resolve_profile_url(
            "dummy-user-data-dir",
            "https://www.linkedin.com/sales/lead/abc123,NAME_SEARCH,xyz",
            full_name="James Castle",
            current_company="Cyber Security Global Alliance",
            location="Toronto, Ontario, Canada",
        )
    )

    assert result == "https://www.linkedin.com/in/jamescastleca"
    assert calls == {
        "full_name": "James Castle",
        "current_company": "Cyber Security Global Alliance",
        "location": "Toronto, Ontario, Canada",
    }
