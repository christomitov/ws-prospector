"""Shared text cleaning and URL normalization utilities."""

from __future__ import annotations

import re


def clean_text(text: str | None) -> str | None:
    """Strip whitespace, collapse internal runs, remove zero-width chars."""
    if not text:
        return None
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def normalize_linkedin_url(url: str | None) -> str | None:
    """Normalize a LinkedIn profile URL to a canonical form."""
    if not url:
        return None
    url = url.strip()
    if url.startswith("//"):
        url = f"https:{url}"
    elif url.startswith("/"):
        url = f"https://www.linkedin.com{url}"
    elif re.match(r"^(?:www\.)?linkedin\.com", url, flags=re.IGNORECASE):
        url = f"https://{url.lstrip('/')}"
    url = url.split("?")[0].rstrip("/")
    url = re.sub(r"https?://(www\.)?linkedin\.com", "https://www.linkedin.com", url)
    if "/in/" not in url and "/sales/lead/" not in url:
        return None
    return url


def extract_connection_degree(text: str | None) -> str | None:
    """Extract '1st', '2nd', '3rd' etc. from badge text."""
    if not text:
        return None
    m = re.search(r"(\d+)(?:st|nd|rd|th)", text)
    if m:
        n = int(m.group(1))
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n, "th")
        return f"{n}{suffix}"
    return None


def extract_mutual_count(text: str | None) -> int | None:
    """Extract mutual connection count from text like '23 mutual connections'."""
    if not text:
        return None
    m = re.search(r"(\d+)\s+(?:\w+\s+)?mutual\s*connection", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def split_title_company(headline: str | None) -> tuple[str | None, str | None]:
    """Best-effort split of 'Title at Company' into (title, company).

    Returns (headline, None) if no separator found.
    """
    if not headline:
        return None, None
    for sep in (" at ", " @ ", " - ", " | "):
        if sep in headline:
            parts = headline.split(sep, 1)
            return clean_text(parts[0]), clean_text(parts[1])
    return headline, None
