"""Best-effort parsing of LinkedIn profile pages and detail subpages."""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse

from .common import clean_text

SECTION_HINT_ALIASES: dict[str, tuple[str, ...]] = {
    "experience": ("experience",),
    "education": ("education",),
    "certifications": (
        "certifications",
        "certification",
        "licenses & certifications",
        "licenses and certifications",
    ),
    "volunteering": ("volunteering", "volunteer experience", "volunteer"),
    "skills": ("skills",),
    "honors": ("honors & awards", "honors and awards", "awards"),
    "languages": ("languages",),
}


def _css_first(el: object, selector: str) -> object | None:
    try:
        if hasattr(el, "css_first"):
            return el.css_first(selector)
        results = el.css(selector)
        return results[0] if results else None
    except Exception:
        return None


def _safe_css(el: object, selector: str) -> list:
    try:
        return el.css(selector) or []
    except Exception:
        return []


def _full_text(el: object) -> str:
    if hasattr(el, "get_all_text"):
        return clean_text(el.get_all_text()) or ""
    if hasattr(el, "text"):
        return clean_text(el.text) or ""
    return ""


def _abs_linkedin_url(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip()
    if value.startswith("//"):
        value = f"https:{value}"
    elif value.startswith("/"):
        value = f"https://www.linkedin.com{value}"
    elif value.startswith("www.linkedin.com"):
        value = f"https://{value}"

    parsed = urlparse(value)
    if parsed.netloc and "linkedin.com" in parsed.netloc:
        return value.split("?")[0]
    return None


def _decode_js_escaped(text: str) -> str:
    try:
        # Flight payload chunks often include escaped unicode/newlines.
        text = bytes(text, "utf-8").decode("unicode_escape")
    except Exception:
        pass
    text = html.unescape(text)
    # Hydration payload snippets can include inline HTML chunks.
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^[>\-\s|•]+", "", text)
    return text


def _get_page_html(page: object) -> str:
    raw = ""
    if hasattr(page, "html_content"):
        raw = page.html_content or ""
    elif hasattr(page, "body"):
        raw = page.body if isinstance(page.body, str) else ""
    return raw if isinstance(raw, str) else ""


def _looks_like_profile_item(text: str, *, section_hint: str) -> bool:
    lower = text.lower()
    if len(text) < 12 or len(text) > 500:
        return False
    if any(
        token in lower
        for token in (
            "http://",
            "https://",
            "www.",
            "linkedin.com/",
            "urn:li:",
            "w3.org",
            "svg",
            "componentkey",
            "data-testid",
            "cachekey",
            "profile_",
            "class=",
            "<div ",
            "<span ",
            "<option ",
            "option value=",
            "object.entries(",
            "function(",
            "aria-",
            "linkedin corporation",
            "cookie",
            "privacy policy",
            "terms of use",
            "invite ",
            "follow ",
            "notifications",
            "skip to main content",
        )
    ):
        return False
    if re.search(r"(?:_[a-z0-9]{6,}\s+){4,}", text):
        return False
    if any(ch in text for ch in ("{", "}", "[", "]", "=>", "$L")):
        return False
    if lower.startswith(
        (
            "show all",
            "see all",
            "add profile section",
            "in progress",
            "loading",
            "skip to",
            "home",
            "notifications",
            "messaging",
            "me",
        )
    ):
        return False
    if text.endswith(" logo"):
        return False
    if not any(ch.isalpha() for ch in text):
        return False
    word_count = len(text.split())
    if section_hint in {"education", "certifications", "volunteering", "skills", "honors", "languages"}:
        min_words = 2
    else:
        min_words = 3
    if word_count < min_words:
        return False
    if word_count > 85:
        return False

    if section_hint in {"education", "certifications", "volunteering", "skills", "honors", "languages"}:
        return word_count >= 2

    # Keep extraction generic and leave semantic interpretation to downstream LLMs.
    if re.search(r"\b(19|20)\d{2}\b", lower):
        return True
    if any(sep in text for sep in (" · ", " - ", " | ", " @ ", " at ")):
        return True
    return word_count >= 5


def _aliases_for_hint(section_hint: str) -> tuple[str, ...]:
    hint = (section_hint or "").strip().lower()
    if hint in SECTION_HINT_ALIASES:
        return SECTION_HINT_ALIASES[hint]
    return (hint,) if hint else ()


def _section_matches_hint(section: object, *, section_hint: str, section_text: str) -> bool:
    aliases = _aliases_for_hint(section_hint)
    if not aliases:
        return False
    lower = section_text.lower()
    head = lower[:180]
    norm_head = re.sub(r"[^a-z0-9]+", " ", head).strip()

    for alias in aliases:
        safe = alias.replace("&", "and").replace(" ", "-")
        if _safe_css(section, f"#{safe}") or _safe_css(section, f"#{alias}"):
            return True

    # New LinkedIn profile pages often omit stable section ids, so use heading text.
    for alias in aliases:
        norm_alias = re.sub(r"[^a-z0-9]+", " ", alias.lower()).strip()
        if norm_alias and f" {norm_alias} " in f" {norm_head} ":
            return True

    attrs = ""
    if hasattr(section, "attrib") and isinstance(section.attrib, dict):
        attrs = " ".join(str(v) for v in section.attrib.values()).lower()
    return any(alias.replace(" ", "") in attrs.replace(" ", "") for alias in aliases)


def _extract_items_from_hydration_payload(
    page: object,
    *,
    section_hint: str,
    max_items: int,
) -> list[str]:
    html_text = _get_page_html(page)
    if not html_text:
        return []

    marker = "ExperienceDetailsSection" if section_hint == "experience" else "EducationDetailsSection"
    markers = list(re.finditer(marker, html_text, flags=re.IGNORECASE))
    if not markers:
        return []

    results: list[str] = []
    seen: set[str] = set()

    def _push(value: str) -> None:
        cleaned = clean_text(_decode_js_escaped(value)) or ""
        if not cleaned:
            return
        if cleaned in seen:
            return
        if not _looks_like_profile_item(cleaned, section_hint=section_hint):
            return
        seen.add(cleaned)
        results.append(cleaned)

    for marker_match in markers:
        start = max(0, marker_match.start() - 140_000)
        end = min(len(html_text), marker_match.start() + 260_000)
        window = html_text[start:end]

        # React flight / SDUI payload is serialized as many JS strings in script tags.
        for raw in re.findall(r'"((?:[^"\\]|\\.)*)"', window):
            _push(raw)
            if len(results) >= max_items:
                return results

    return results[:max_items]


def _extract_items_from_section_on_profile_page(
    page: object,
    *,
    section_hint: str,
    max_items: int,
) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()

    sections = _safe_css(page, "div[role='main'] section")
    if not sections:
        sections = _safe_css(page, "main section")
    if not sections:
        sections = _safe_css(page, "section")

    for section in sections:
        section_text = _full_text(section) or ""
        if not _section_matches_hint(section, section_hint=section_hint, section_text=section_text):
            continue

        nodes: list[object] = []
        for selector in (
            "li",
            "p",
            "span[aria-hidden='true']",
            "div[aria-hidden='true']",
            "a",
        ):
            nodes.extend(_safe_css(section, selector))
        for node in nodes:
            text = clean_text(_full_text(node)) or ""
            if not text or text in seen:
                continue
            if not _looks_like_profile_item(text, section_hint=section_hint):
                continue
            seen.add(text)
            rows.append(text)
            if len(rows) >= max_items:
                return rows
    return rows[:max_items]


def parse_profile_summary(page: object) -> dict:
    """Extract top-of-profile summary fields."""
    name = None
    headline = None
    location = None

    name_el = _css_first(page, "h1")
    if name_el:
        name = clean_text(name_el.text)

    headline_selectors = [
        "main section div.text-body-medium",
        "main div.ph5 div.text-body-medium",
        "section div.text-body-medium",
    ]
    for selector in headline_selectors:
        el = _css_first(page, selector)
        text = clean_text(el.text if el else None)
        if text:
            headline = text
            break

    location_selectors = [
        "main section span.text-body-small.inline.t-black--light.break-words",
        "main div.ph5 span.text-body-small",
        "section span.text-body-small",
    ]
    for selector in location_selectors:
        el = _css_first(page, selector)
        text = clean_text(el.text if el else None)
        if text:
            location = text
            break

    return {
        "name": name,
        "headline": headline,
        "location": location,
    }


def parse_about_text(page: object, *, max_chars: int = 4000) -> str | None:
    """Extract profile About section text."""
    candidate_selectors = [
        "section:has(#about) div.inline-show-more-text",
        "section:has(#about) div[dir='ltr']",
        "section:has(#about) span[aria-hidden='true']",
    ]
    for selector in candidate_selectors:
        el = _css_first(page, selector)
        if not el:
            continue
        text = _full_text(el)
        if text and len(text) > 20:
            return text[:max_chars]

    # Fallback: inspect section blocks and pick one that looks like About.
    sections = page.css("main section") or page.css("section") or []
    for section in sections:
        txt = _full_text(section)
        if not txt or len(txt) < 25:
            continue
        lower = txt.lower()
        if not lower.startswith("about") and "\nabout" not in lower and " about " not in lower[:120]:
            continue
        cleaned = re.sub(r"^about\s*", "", txt, flags=re.IGNORECASE).strip()
        if cleaned:
            return cleaned[:max_chars]

    return None


def parse_detail_list_items(
    page: object,
    *,
    max_items: int = 12,
    section_hint: str = "",
) -> list[str]:
    """Extract normalized list rows from details pages (experience/education)."""
    selectors = [
        "li.pvs-list__paged-list-item",
        "main li.artdeco-list__item",
        "main li",
    ]

    rows: list[str] = []
    seen: set[str] = set()

    def _push(text: str) -> None:
        text = clean_text(text) or ""
        if not text:
            return
        lower = text.lower()
        if lower.startswith(("show all", "see all", "add profile section")):
            return
        if not _looks_like_profile_item(text, section_hint=section_hint or "experience"):
            return
        if text in seen:
            return
        seen.add(text)
        rows.append(text)

    for selector in selectors:
        items = page.css(selector) or []
        if not items:
            continue
        for item in items:
            _push(_full_text(item))
            if len(rows) >= max_items:
                return rows

    # Fallback: when detail nodes are lazy/paginated and not rendered as static <li>,
    # parse likely entries from LinkedIn hydration payload near the target section.
    if section_hint in {"experience", "education"}:
        payload_rows = _extract_items_from_hydration_payload(
            page, section_hint=section_hint, max_items=max_items
        )
        for row in payload_rows:
            _push(row)
            if len(rows) >= max_items:
                return rows

    return rows[:max_items]


def parse_profile_section_items(
    profile_page: object,
    *,
    section_hint: str,
    max_items: int,
) -> list[str]:
    """Extract section rows directly from profile main page (fallback path)."""
    rows = _extract_items_from_section_on_profile_page(
        profile_page, section_hint=section_hint, max_items=max_items
    )
    if rows:
        return rows[:max_items]
    return _extract_items_from_hydration_payload(
        profile_page,
        section_hint=section_hint,
        max_items=max_items,
    )


def parse_featured_posts(page: object, *, max_items: int = 5) -> list[dict]:
    """Extract featured post snippets from the main profile page."""
    results: list[dict] = []
    seen_urls: set[str] = set()

    sections = _safe_css(page, "div[role='main'] section")
    if not sections:
        sections = _safe_css(page, "main section")
    if not sections:
        sections = _safe_css(page, "section")

    def _append(url: str | None, text: str | None) -> None:
        if len(results) >= max_items:
            return
        clean = clean_text(text)
        if not clean or len(clean) < 20:
            return
        abs_url = _abs_linkedin_url(url)
        if abs_url and "/feed/update/" not in abs_url and "/posts/" not in abs_url:
            return
        if abs_url and abs_url in seen_urls:
            return
        if abs_url:
            seen_urls.add(abs_url)
        results.append({"url": abs_url, "text": clean[:1200]})

    for section in sections:
        text = (_full_text(section) or "").lower()
        if "featured" not in text[:280]:
            continue
        links = _safe_css(section, "a[href*='/feed/update/'], a[href*='/posts/']")
        for link in links:
            href = link.attrib.get("href") if hasattr(link, "attrib") else None
            _append(href, _full_text(link))
            if len(results) >= max_items:
                return results

        # Fallback when link cards are missing: keep paragraph snippets from featured section.
        for node in _safe_css(section, "p"):
            _append(None, _full_text(node))
            if len(results) >= max_items:
                return results

    return results


def parse_activity_posts(page: object, *, max_items: int = 5) -> list[dict]:
    """Extract activity post snippets from the main profile page Activity section."""
    results: list[dict] = []
    seen_urls: set[str] = set()

    sections = _safe_css(page, "div[role='main'] section")
    if not sections:
        sections = _safe_css(page, "main section")
    if not sections:
        sections = _safe_css(page, "section")

    def _append(url: str | None, text: str | None) -> None:
        if len(results) >= max_items:
            return
        clean = clean_text(text)
        if not clean or len(clean) < 20:
            return
        abs_url = _abs_linkedin_url(url)
        if abs_url and "/feed/update/" not in abs_url and "/posts/" not in abs_url:
            return
        if abs_url and abs_url in seen_urls:
            return
        if abs_url:
            seen_urls.add(abs_url)
        results.append({"url": abs_url, "text": clean[:1200]})

    for section in sections:
        text = (_full_text(section) or "").lower()
        if "activity" not in text[:220]:
            continue
        if "posts" not in text[:320]:
            continue
        links = _safe_css(section, "a[href*='/feed/update/'], a[href*='/posts/']")
        for link in links:
            href = link.attrib.get("href") if hasattr(link, "attrib") else None
            _append(href, _full_text(link))
            if len(results) >= max_items:
                return results
        break

    return results


def parse_recent_posts(page: object, *, max_items: int = 5) -> list[dict]:
    """Extract recent post snippets from activity page."""
    results: list[dict] = []
    seen_urls: set[str] = set()

    card_selectors = [
        "div.feed-shared-update-v2",
        "article",
        "main li",
    ]

    def _append(url: str | None, text: str | None) -> None:
        if len(results) >= max_items:
            return
        clean = clean_text(text)
        if not clean or len(clean) < 20:
            return
        abs_url = _abs_linkedin_url(url)
        if abs_url and abs_url in seen_urls:
            return
        if abs_url:
            seen_urls.add(abs_url)
        results.append({"url": abs_url, "text": clean[:1200]})

    for selector in card_selectors:
        cards = page.css(selector) or []
        for card in cards:
            link = _css_first(card, "a[href*='/feed/update/']") or _css_first(card, "a[href*='/posts/']")
            href = link.attrib.get("href") if link and hasattr(link, "attrib") else None
            _append(href, _full_text(card))
            if len(results) >= max_items:
                return results

    # Fallback: no post cards found, still expose raw update links.
    links = page.css("a[href*='/feed/update/'], a[href*='/posts/']") or []
    for link in links:
        href = link.attrib.get("href") if hasattr(link, "attrib") else None
        text = _full_text(link)
        _append(href, text)
        if len(results) >= max_items:
            break

    return results
