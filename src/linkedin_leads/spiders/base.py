"""Base spider with rate limiting, block detection, and session configuration."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path

from scrapling.fetchers import StealthyFetcher

from ..config import BLOCK_WAIT, DATA_DIR, DEFAULT_DELAY, MAX_RETRIES
from ..models import Lead

logger = logging.getLogger(__name__)

DEBUG_HTML_DIR = DATA_DIR / "debug_html"

# Block-detection signals
_BLOCK_STATUSES = {429, 999, 403}
_BLOCK_TEXTS = [
    "commercial use limit",
    "you've reached the commercial use limit",
    "we've restricted your access",
]
_BLOCK_URL_FRAGMENTS = ["/login", "/checkpoint", "/challenge"]


class LinkedInSpider(ABC):
    """Base class for all LinkedIn spiders."""

    download_delay: float = DEFAULT_DELAY
    max_retries: int = MAX_RETRIES
    headless: bool = True

    def __init__(self, user_data_dir: str, max_pages: int = 5) -> None:
        self.user_data_dir = user_data_dir
        self.max_pages = max_pages
        self._last_request_time: float = 0

    @abstractmethod
    def build_url(self, page: int) -> str:
        """Return the URL for the given page number."""

    @abstractmethod
    def parse_page(self, page_response: object) -> list[Lead]:
        """Extract leads from a fetched page."""

    async def crawl(self, on_progress: object | None = None) -> list[Lead]:
        """Crawl all pages, yielding leads. Calls on_progress(found, page) if provided."""
        all_leads: list[Lead] = []
        for page_num in range(1, self.max_pages + 1):
            url = self.build_url(page_num)
            logger.info("Fetching page %d: %s", page_num, url)

            response = await self._fetch_with_retry(url)
            if response is None:
                logger.warning("Stopping at page %d — blocked or no response", page_num)
                break

            self._save_debug_html(response, page_num)
            leads = self.parse_page(response)
            if not leads:
                logger.info("No leads found on page %d — end of results", page_num)
                break

            all_leads.extend(leads)
            if on_progress:
                await on_progress(len(all_leads), page_num)

            await self._throttle()

        return all_leads

    async def _fetch_with_retry(self, url: str) -> object | None:
        from ..browser_lock import browser_lock

        for attempt in range(1, self.max_retries + 1):
            await self._throttle()
            async with browser_lock:
                response = await asyncio.to_thread(self._fetch, url)
                if response is not None and self._should_retry_headful(response, url):
                    logger.info(
                        "Headless Sales Nav response was loading-only; retrying in headed mode for %s",
                        url,
                    )
                    response = await asyncio.to_thread(self._fetch, url, False)
            if response is None:
                return None
            if not self._is_blocked(response):
                return response
            logger.warning(
                "Blocked on attempt %d/%d — waiting %.0fs",
                attempt, self.max_retries, BLOCK_WAIT,
            )
            await asyncio.sleep(BLOCK_WAIT)
        logger.error("Max retries exceeded for %s", url)
        return None

    def _fetch(self, url: str, headless: bool | None = None) -> object | None:
        if headless is None:
            headless = self.headless
        try:
            return StealthyFetcher.fetch(
                url,
                headless=headless,
                real_chrome=True,
                user_data_dir=self.user_data_dir,
                block_images=True,
                disable_resources=False,
                page_action=_wait_for_results,
            )
        except Exception:
            logger.exception("Fetch failed for %s", url)
            return None

    def _should_retry_headful(self, response: object, url: str) -> bool:
        """Detect headless Sales Nav skeleton pages and retry once in headed mode."""
        if not self.headless:
            return False
        if "/sales/search/people" not in url:
            return False

        html = ""
        if hasattr(response, "html_content"):
            html = response.html_content or ""
        elif hasattr(response, "text"):
            html = response.text or ""

        if not html:
            return False

        has_loader = "initial-load-animation" in html or "salesnav-image" in html
        has_leads = "/sales/lead/" in html or 'data-x-search-result="LEAD"' in html
        return has_loader and not has_leads

    def _save_debug_html(self, response: object, page_num: int) -> None:
        """Save raw HTML to disk for debugging selectors."""
        if os.getenv("WS_PROSPECTOR_SAVE_DEBUG_HTML", "1").strip().lower() in {"0", "false", "no"}:
            return
        try:
            DEBUG_HTML_DIR.mkdir(parents=True, exist_ok=True)
            html = ""
            if hasattr(response, "html_content"):
                html = response.html_content
            elif hasattr(response, "text"):
                html = response.text or ""
            elif hasattr(response, "body"):
                html = response.body if isinstance(response.body, str) else response.body.decode("utf-8", errors="replace")
            path = DEBUG_HTML_DIR / f"page_{page_num}.html"
            path.write_text(html, encoding="utf-8")
            logger.info("Debug HTML saved to %s (%d bytes)", path, len(html))
        except Exception:
            logger.debug("Failed to save debug HTML", exc_info=True)

    def _is_blocked(self, response: object) -> bool:
        if hasattr(response, "status") and response.status in _BLOCK_STATUSES:
            return True
        url = str(response.url) if hasattr(response, "url") else ""
        if any(frag in url for frag in _BLOCK_URL_FRAGMENTS):
            return True
        text = ""
        if hasattr(response, "text"):
            text = (response.text or "")[:5000].lower()
        elif hasattr(response, "get_text"):
            text = (response.get_text() or "")[:5000].lower()
        return any(bt in text for bt in _BLOCK_TEXTS)

    async def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.download_delay:
            await asyncio.sleep(self.download_delay - elapsed)
        self._last_request_time = time.monotonic()


def _wait_for_results(page: object) -> None:
    """Playwright page_action: wait for results to render."""
    import time as _time

    def _count(selector: str) -> int:
        try:
            return page.locator(selector).count()
        except Exception:
            return 0

    try:
        url = str(getattr(page, "url", "") or "")

        # Sales Navigator is JS-heavy and often returns only loading skeletons
        # unless we wait for LEAD rows to mount.
        if "/sales/search/people" in url:
            for _ in range(12):
                if (
                    _count("div[data-x-search-result='LEAD']") > 0
                    or _count("a[data-lead-search-result*='profile-link']") > 0
                    or _count("a[href*='/sales/lead/']") > 0
                ):
                    break
                page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.55)")
                _time.sleep(1.0)
            page.evaluate("window.scrollTo(0, 0)")
            _time.sleep(0.5)
            return

        # LinkedIn people/company pages.
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        _time.sleep(1.0)
        page.evaluate("window.scrollTo(0, 0)")
        _time.sleep(0.5)
    except Exception:
        pass
