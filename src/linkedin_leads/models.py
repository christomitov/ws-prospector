"""Lead data model."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class LeadSource(str, Enum):
    linkedin_search = "linkedin_search"
    sales_navigator = "sales_navigator"
    company_employees = "company_employees"


class Lead(BaseModel):
    linkedin_url: str | None = None
    full_name: str
    headline: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    location: str | None = None
    connection_degree: str | None = None
    mutual_connections: int | None = None
    source: LeadSource
    search_query: str | None = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("linkedin_url", mode="before")
    @classmethod
    def normalize_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if v.startswith("//"):
            v = f"https:{v}"
        elif v.startswith("/"):
            v = f"https://www.linkedin.com{v}"
        elif re.match(r"^(?:www\.)?linkedin\.com", v, flags=re.IGNORECASE):
            v = f"https://{v.lstrip('/')}"
        v = v.split("?")[0].rstrip("/")
        v = re.sub(r"https?://(www\.)?linkedin\.com", "https://www.linkedin.com", v)
        return v

    @property
    def dedup_key(self) -> str:
        if self.linkedin_url:
            return self.linkedin_url
        return f"{self.full_name}|{self.current_company or ''}"


class SearchRequest(BaseModel):
    keywords: str = ""
    title: str = ""
    location: str = ""
    industry: str = ""
    company: str = ""
    max_pages: int = Field(default=5, ge=1, le=100)
