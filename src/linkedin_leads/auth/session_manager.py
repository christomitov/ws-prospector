"""Browser login, cookie persistence, and session health check."""

from __future__ import annotations

import asyncio
import logging
import shutil
from enum import Enum
from pathlib import Path

from scrapling.fetchers import StealthyFetcher

from ..config import SESSIONS_DIR, ensure_dirs

logger = logging.getLogger(__name__)


class SessionStatus(str, Enum):
    connected = "connected"
    expired = "expired"
    unknown = "unknown"


class SessionManager:
    """Manages a persistent browser session for LinkedIn."""

    def __init__(self) -> None:
        ensure_dirs()
        self._user_data_dir = str(SESSIONS_DIR)
        self._status = SessionStatus.unknown

    @property
    def status(self) -> SessionStatus:
        return self._status

    @property
    def user_data_dir(self) -> str:
        return self._user_data_dir

    async def login(self) -> SessionStatus:
        """Open a visible browser for manual LinkedIn login.

        Uses patchright (Playwright fork) directly so the browser stays open
        for interactive login — StealthyFetcher.fetch() is one-shot and
        closes the browser before the user can finish typing.

        The browser uses a persistent profile (same user_data_dir that
        StealthyFetcher will use later) so cookies survive across runs.
        """
        logger.info("Opening browser for LinkedIn login...")
        from ..browser_lock import browser_lock

        def _do_login() -> SessionStatus:
            from patchright.sync_api import sync_playwright

            with sync_playwright() as pw:
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=self._user_data_dir,
                    channel="chrome",
                    headless=False,
                    viewport={"width": 1280, "height": 900},
                    screen={"width": 1280, "height": 900},
                    ignore_https_errors=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                )
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

                    # Wait up to 3 minutes for the user to complete login
                    # (handles typing, 2FA, CAPTCHA, etc.)
                    try:
                        page.wait_for_url(
                            lambda url: any(p in url for p in ("/feed", "/mynetwork", "/in/", "/sales")),
                            timeout=180_000,
                        )
                        logger.info("Login successful — landed on %s", page.url)
                        return SessionStatus.connected
                    except Exception:
                        # Check if they ended up on a valid page anyway
                        url = page.url
                        if "/feed" in url or "/mynetwork" in url:
                            return SessionStatus.connected
                        logger.warning("Login wait timed out at %s", url)
                        return SessionStatus.expired
                finally:
                    context.close()

        async with browser_lock:
            self._status = await asyncio.to_thread(_do_login)
        return self._status

    async def check_status(self, *, log_errors: bool = True) -> SessionStatus:
        """Check whether the saved session is still valid.

        Fetches /feed/ headlessly — if LinkedIn redirects to /login,
        the session is expired.
        """
        from ..browser_lock import browser_lock

        def _check() -> SessionStatus:
            try:
                page = StealthyFetcher.fetch(
                    "https://www.linkedin.com/feed/",
                    headless=True,
                    real_chrome=True,
                    user_data_dir=self._user_data_dir,
                    block_images=True,
                    disable_resources=True,
                )
                if page is None:
                    return SessionStatus.expired
                url = str(page.url) if hasattr(page, "url") else ""
                if "/login" in url or "/checkpoint" in url:
                    return SessionStatus.expired
                if page.status == 200:
                    return SessionStatus.connected
                return SessionStatus.expired
            except Exception:
                if log_errors:
                    logger.exception("Session check failed")
                else:
                    logger.debug("Session check failed", exc_info=True)
                return SessionStatus.unknown

        async with browser_lock:
            self._status = await asyncio.to_thread(_check)
        return self._status

    async def logout(self) -> SessionStatus:
        """Clear persisted LinkedIn session data."""
        from ..browser_lock import browser_lock

        def _do_logout() -> SessionStatus:
            session_dir = Path(self._user_data_dir)
            if session_dir.exists():
                shutil.rmtree(session_dir, ignore_errors=True)
            session_dir.mkdir(parents=True, exist_ok=True)
            return SessionStatus.unknown

        async with browser_lock:
            self._status = await asyncio.to_thread(_do_logout)
        return self._status
