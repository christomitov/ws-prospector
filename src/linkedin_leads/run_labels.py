"""Helpers for concise run labels in DB/UI."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def summarize_text(text: str | None, *, max_len: int = 140) -> str:
    value = _collapse(text or "")
    if not value:
        return ""
    if len(value) <= max_len:
        return value
    return f"{value[: max_len - 1].rstrip()}..."


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        key = v.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def _sales_nav_terms(url: str, *, max_terms: int = 5) -> list[str]:
    # The encoded Sales Nav query payload carries filters as text:<value>.
    raw = unquote(unquote(url))
    parsed = urlparse(url)
    q = parse_qs(parsed.query).get("query", [""])[0]
    blob = unquote(unquote(q)) if q else raw
    terms = [unquote(t) for t in re.findall(r"text:([^,\)]+)", blob)]
    cleaned = _dedupe([_collapse(t) for t in terms if _collapse(t)])
    return cleaned[:max_terms]


def summarize_url(url: str, *, source: str | None = None, max_len: int = 140) -> str:
    parsed = urlparse(url)
    path = parsed.path or ""
    qs = parse_qs(parsed.query)
    src = (source or "").lower()

    if "/sales/search/people" in path or src == "sales_navigator":
        terms = _sales_nav_terms(url)
        if terms:
            return summarize_text(f"Sales Nav: {', '.join(terms)}", max_len=max_len)
        return "Sales Nav URL search"

    if "/search/results/people" in path:
        keywords = _collapse(unquote((qs.get("keywords") or [""])[0]))
        if keywords:
            return summarize_text(f"LinkedIn people: {keywords}", max_len=max_len)
        return "LinkedIn people search URL"

    if "/company/" in path and "/people" in path:
        slug = path.split("/company/", 1)[-1].split("/", 1)[0]
        return summarize_text(f"Company people: {slug}", max_len=max_len)

    host = parsed.netloc or "linkedin.com"
    short = f"{host}{path}"
    return summarize_text(short, max_len=max_len)


def summarize_request(
    *,
    source: str | None = None,
    keywords: str = "",
    title: str = "",
    location: str = "",
    industry: str = "",
    company: str = "",
    max_len: int = 140,
) -> str:
    bits = []
    if keywords.strip():
        bits.append(keywords.strip())
    if title.strip():
        bits.append(f"title:{title.strip()}")
    if location.strip():
        bits.append(f"location:{location.strip()}")
    if company.strip():
        bits.append(f"company:{company.strip()}")
    if industry.strip():
        bits.append(f"industry:{industry.strip()}")

    base = ", ".join(bits) if bits else "search"
    if source == "sales_navigator":
        base = f"Sales Nav query: {base}"
    elif source == "company_employees":
        base = f"Company employees: {base}"
    else:
        base = f"LinkedIn search: {base}"
    return summarize_text(base, max_len=max_len)
