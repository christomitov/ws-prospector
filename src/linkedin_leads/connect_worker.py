"""Background worker that sends connect requests with human-like jitter.

Runs continuously by default with random intervals and a conservative daily cap
(default 10). Business-hours-only behavior is optional via environment
variables. Uses patchright directly (not StealthyFetcher) to avoid browser
profile lock conflicts with the scraper.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import time as _time
from datetime import date, datetime, time
from urllib.parse import quote, unquote, urlparse

from .storage import LeadStore

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


DEFAULT_CONNECT_SETTINGS = {
    "daily_limit": max(1, _env_int("LI_CONNECT_DAILY_LIMIT", 10)),
    "min_delay_seconds": max(5.0, _env_float("LI_CONNECT_MIN_DELAY_SECONDS", 90.0)),
    "max_delay_seconds": max(5.0, _env_float("LI_CONNECT_MAX_DELAY_SECONDS", 300.0)),
    "business_hours_only": _env_bool("LI_CONNECT_BUSINESS_HOURS_ONLY", False),
    "biz_start_hour": min(23, max(0, _env_int("LI_CONNECT_BIZ_START_HOUR", 9))),
    "biz_end_hour": min(23, max(0, _env_int("LI_CONNECT_BIZ_END_HOUR", 17))),
}


def _to_int(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


def normalize_connect_settings(raw: dict | None) -> dict:
    data = raw or {}
    daily_limit = max(1, _to_int(data.get("daily_limit"), DEFAULT_CONNECT_SETTINGS["daily_limit"]))
    min_delay = max(5.0, _to_float(data.get("min_delay_seconds"), DEFAULT_CONNECT_SETTINGS["min_delay_seconds"]))
    max_delay = max(min_delay, _to_float(data.get("max_delay_seconds"), DEFAULT_CONNECT_SETTINGS["max_delay_seconds"]))
    biz_start_hour = min(23, max(0, _to_int(data.get("biz_start_hour"), DEFAULT_CONNECT_SETTINGS["biz_start_hour"])))
    biz_end_hour = min(23, max(0, _to_int(data.get("biz_end_hour"), DEFAULT_CONNECT_SETTINGS["biz_end_hour"])))
    business_hours_only = _to_bool(data.get("business_hours_only"), DEFAULT_CONNECT_SETTINGS["business_hours_only"])
    return {
        "daily_limit": daily_limit,
        "min_delay_seconds": min_delay,
        "max_delay_seconds": max_delay,
        "business_hours_only": business_hours_only,
        "biz_start_hour": biz_start_hour,
        "biz_end_hour": biz_end_hour,
    }


class ConnectWorker:
    """Background worker that drains the connect queue."""

    def __init__(self, user_data_dir: str, store: LeadStore) -> None:
        self.user_data_dir = user_data_dir
        self.store = store
        self._running = False
        self._task: asyncio.Task | None = None
        self._wake_event = asyncio.Event()
        self._paused = False
        self._last_sent: str | None = None
        self._sends_today: int = 0
        self._today: date | None = None
        self._settings = self._load_settings()

    def _load_settings(self) -> dict:
        get_settings = getattr(self.store, "get_connect_settings", None)
        stored = get_settings() if callable(get_settings) else {}
        return normalize_connect_settings(stored)

    def get_settings(self) -> dict:
        self._settings = self._load_settings()
        return dict(self._settings)

    def update_settings(self, updates: dict) -> dict:
        merged = {**self._load_settings(), **updates}
        normalized = normalize_connect_settings(merged)
        save_settings = getattr(self.store, "save_connect_settings", None)
        if callable(save_settings):
            save_settings(normalized)
        self._settings = normalized
        return dict(normalized)

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    @property
    def is_paused(self) -> bool:
        return self._paused

    def start(self) -> None:
        if self.is_running:
            return
        self._running = True
        self._paused = False
        self._wake_event.set()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Connect worker started")

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        self._wake_event.set()
        logger.info("Connect worker stopped")

    def pause(self) -> None:
        self._paused = True
        logger.info("Connect worker paused")

    def resume(self) -> None:
        self._paused = False
        self._wake_event.set()
        logger.info("Connect worker resumed")

    def nudge(self) -> None:
        """Wake the run loop so it can process queue changes immediately."""
        self._wake_event.set()

    def status(self) -> dict:
        queue = self.store.connect_queue_stats()
        sends_today = self.store.connect_sent_count_for_local_day(date.today())
        settings = self.get_settings()
        biz_start = time(settings["biz_start_hour"], 0)
        biz_end = time(settings["biz_end_hour"], 0)
        # Keep in-memory counter aligned with persisted source of truth.
        self._sends_today = sends_today
        return {
            "running": self.is_running,
            "paused": self._paused,
            "last_sent": self._last_sent,
            "sends_today": sends_today,
            "daily_limit": settings["daily_limit"],
            "min_delay_seconds": settings["min_delay_seconds"],
            "max_delay_seconds": settings["max_delay_seconds"],
            "business_hours_only": settings["business_hours_only"],
            "biz_start_hour": settings["biz_start_hour"],
            "biz_end_hour": settings["biz_end_hour"],
            "business_start": biz_start.strftime("%H:%M"),
            "business_end": biz_end.strftime("%H:%M"),
            **queue,
        }

    async def _run_loop(self) -> None:
        """Main loop: pick next pending request, send it, wait with jitter."""
        while self._running:
            try:
                # Reset daily counter at midnight
                today = date.today()
                if self._today != today:
                    self._today = today
                    self._sends_today = self.store.connect_sent_count_for_local_day(today)

                if self._paused:
                    await self._sleep_with_wake(5)
                    continue

                settings = self._load_settings()
                self._settings = settings
                daily_limit = settings["daily_limit"]

                if settings["business_hours_only"] and not self._is_business_hours(settings):
                    logger.debug("Outside business hours — sleeping 60s")
                    await self._sleep_with_wake(60)
                    continue

                if self._sends_today >= daily_limit:
                    logger.info("Daily limit reached (%d/%d) — waiting for tomorrow", self._sends_today, daily_limit)
                    await self._sleep_with_wake(300)
                    continue

                item = self.store.next_pending_connect()
                if item is None:
                    logger.debug("Connect queue empty — sleeping 30s")
                    await self._sleep_with_wake(30)
                    continue

                # Acquire the global browser lock so we don't conflict with scrapers
                from .browser_lock import browser_lock
                async with browser_lock:
                    sent = await self._send_connect(item)

                if sent:
                    self._sends_today += 1

                # Random jitter between requests regardless of success
                delay = random.uniform(settings["min_delay_seconds"], settings["max_delay_seconds"])
                logger.info("Sent %d/%d today. Next connect in %.0fs", self._sends_today, daily_limit, delay)
                await self._sleep_with_wake(delay)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Connect worker error — retrying in 60s")
                await self._sleep_with_wake(60)

    async def _sleep_with_wake(self, seconds: float) -> None:
        """Sleep for duration unless a nudge arrives first."""
        if seconds <= 0:
            return
        self._wake_event.clear()
        try:
            await asyncio.wait_for(self._wake_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    def _is_business_hours(self, settings: dict) -> bool:
        biz_start = time(settings["biz_start_hour"], 0)
        biz_end = time(settings["biz_end_hour"], 0)
        now = datetime.now().time()
        if biz_start <= biz_end:
            return biz_start <= now <= biz_end
        # Support windows that cross midnight (e.g., 22:00 -> 06:00).
        return now >= biz_start or now <= biz_end

    async def _send_connect(self, item: dict) -> bool:
        """Send a single connect request using patchright directly. Returns True on verified success."""
        queue_id = item["id"]
        url = item["linkedin_url"]
        name = item["full_name"]
        note = item.get("note")

        logger.info("Sending connect request to %s (%s)", name, url)

        try:
            success = await asyncio.to_thread(self._do_connect, url, note)
            if success:
                self.store.mark_connect(queue_id, "sent")
                self._last_sent = name
                logger.info("Connect request verified sent to %s", name)
                return True
            else:
                self.store.mark_connect(queue_id, "failed", error="Connect button not found or send not verified")
                logger.warning("Failed to connect with %s", name)
                return False
        except Exception as e:
            self.store.mark_connect(queue_id, "failed", error=str(e))
            logger.exception("Failed to send connect request to %s", name)
            return False

    def _save_screenshot(self, page: object, name: str) -> None:
        """Save a debug screenshot."""
        try:
            from .config import DATA_DIR
            ss_dir = DATA_DIR / "debug_html"
            ss_dir.mkdir(parents=True, exist_ok=True)
            path = ss_dir / f"{name}.png"
            page.screenshot(path=str(path), full_page=True)
            logger.info("Screenshot saved: %s", path)
        except Exception:
            logger.debug("Failed to save screenshot %s", name, exc_info=True)

    def _save_html(self, page: object, name: str) -> None:
        """Save the full page HTML for debugging selectors."""
        try:
            from .config import DATA_DIR
            ss_dir = DATA_DIR / "debug_html"
            ss_dir.mkdir(parents=True, exist_ok=True)
            path = ss_dir / f"{name}.html"
            html = page.content()
            path.write_text(html, encoding="utf-8")
            logger.info("HTML saved: %s (%d bytes)", path, len(html))
        except Exception:
            logger.debug("Failed to save HTML %s", name, exc_info=True)

    def _human_delay(self, low: float, high: float, label: str = "") -> None:
        """Sleep for a random duration to mimic human behaviour."""
        delay = random.uniform(low, high)
        if label:
            logger.debug("Human delay (%.1fs) — %s", delay, label)
        _time.sleep(delay)

    def _do_connect(self, profile_url: str, note: str | None) -> bool:
        """Open profile page and click Connect using patchright directly.

        Uses patchright instead of StealthyFetcher to avoid browser profile
        lock conflicts — only one Chromium instance can use a profile dir
        at a time.
        """
        from patchright.sync_api import sync_playwright

        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                channel="chrome",
                headless=True,
                viewport={"width": 1280, "height": 900},
                ignore_https_errors=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(profile_url, wait_until="domcontentloaded")

                # Wait for page to load like a real person would
                self._human_delay(3, 5, "page load")

                # Scroll around to look natural — a person would read the profile
                page.evaluate("window.scrollTo(0, 300)")
                self._human_delay(2, 4, "reading top section")
                page.evaluate("window.scrollTo(0, 600)")
                self._human_delay(1.5, 3, "scrolling down")
                page.evaluate("window.scrollTo(0, 0)")
                self._human_delay(1, 2, "scrolling back up")

                self._save_screenshot(page, "connect_1_loaded")
                self._save_html(page, "connect_profile")

                # Check if already connected / pending
                if self._is_already_connected(page):
                    logger.info("Already connected or pending — skipping %s", profile_url)
                    return True

                # Dwell on the profile a bit before acting — like reading their headline
                self._human_delay(3, 8, "reading profile before connect")

                # Find the Connect button
                connect_btn = self._find_connect_button(page)

                if not connect_btn:
                    # Try clicking "More" to reveal Connect in dropdown
                    connect_btn = self._try_more_menu(page)

                used_direct_invite_fallback = False
                if not connect_btn:
                    # Fallback: construct LinkedIn's invite URL directly from the
                    # profile vanity slug and continue through the same send flow.
                    direct_invite_url = self._build_direct_invite_url(profile_url)
                    if not direct_invite_url:
                        logger.warning("Connect button not found on %s", profile_url)
                        self._save_screenshot(page, "connect_fail_no_button")
                        return False
                    logger.info("Connect button not found; using direct invite URL fallback: %s", direct_invite_url)
                    page.goto(direct_invite_url, wait_until="domcontentloaded")
                    used_direct_invite_fallback = True
                    self._human_delay(2, 4, "waiting on direct invite page")

                if connect_btn:
                    # Small pause before clicking — like moving the mouse over
                    self._human_delay(0.5, 1.5, "hovering before click")

                    # The main Connect is an <a> with href to /preload/custom-invite/.
                    # A normal click can be blocked by overlay elements, so extract
                    # the href and navigate directly — same end result, more reliable.
                    href = connect_btn.get_attribute("href")
                    if href:
                        invite_url = href if href.startswith("http") else f"https://www.linkedin.com{href}"
                        logger.info("Navigating to invite page: %s", invite_url)
                        page.goto(invite_url, wait_until="domcontentloaded")
                    else:
                        logger.info("No href — clicking Connect directly...")
                        connect_btn.click(force=True)
                    self._human_delay(2, 4, "waiting after connect click")

                self._save_screenshot(page, "connect_2_after_click")
                self._save_html(page, "connect_after_click")

                # The main Connect is an <a> that may navigate to /preload/custom-invite/
                # or open a modal. Handle both paths.
                current_url = page.url
                logger.info("After click, URL is: %s", current_url)

                if "/custom-invite" in current_url or "/preload/" in current_url:
                    # We navigated to the invite page
                    sent = self._handle_invite_page(page, note)
                else:
                    # A modal appeared on the same page
                    sent = self._handle_connect_modal(page, note)
                    if not sent and not used_direct_invite_fallback:
                        # Last-chance fallback for profiles where Connect only lives
                        # behind secondary UI states.
                        direct_invite_url = self._build_direct_invite_url(profile_url)
                        if direct_invite_url:
                            logger.info("Modal path failed; retrying via direct invite URL: %s", direct_invite_url)
                            page.goto(direct_invite_url, wait_until="domcontentloaded")
                            self._human_delay(1.5, 3, "waiting on direct invite retry")
                            sent = self._handle_invite_page(page, note)

                if not sent:
                    self._save_screenshot(page, "connect_fail_send")
                    return False

                self._human_delay(1.5, 3, "post-send")
                self._save_screenshot(page, "connect_3_after_send")

                # Verify: check we ended up somewhere that indicates success
                if self._verify_sent(page, profile_url):
                    logger.info("Verified: connection request sent to %s", profile_url)
                    return True
                else:
                    logger.warning("Could not verify connect was sent for %s", profile_url)
                    self._save_screenshot(page, "connect_fail_verify")
                    return False

            finally:
                context.close()

    def _is_already_connected(self, page: object) -> bool:
        """Check if the profile appears already connected/pending."""
        selectors = [
            'div[role="toolbar"] div[data-view-name="relationship-building-button"] :is(a, button):has-text("Pending"):visible',
            'div[role="toolbar"] :is(a, button)[aria-label*="Pending" i]:visible',
            'div[role="toolbar"] :is(a, button)[aria-label*="Connected" i]:visible',
            'section[componentkey*="Topcard"] :is(a, button)[aria-label*="Pending" i]:visible',
            'section[componentkey*="Topcard"] :is(a, button)[aria-label*="Connected" i]:visible',
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=1500):
                    logger.debug("Found Pending via: %s", sel)
                    return True
            except Exception:
                continue
        return False

    def _find_connect_button(self, page: object) -> object | None:
        """Find the main profile Connect button.

        Prefer top-card/toolbar selectors first to avoid matching sidebar
        recommendation cards lower on the page.
        """
        selectors = [
            'div[role="toolbar"] div[data-view-name="edge-creation-connect-action"] :is(a, button):visible',
            'div[role="toolbar"] div[data-view-name="relationship-building-button"] :is(a, button)[aria-label*="connect" i]:visible',
            'div[role="toolbar"] :is(a, button)[aria-label*="Invite"][aria-label*="connect" i]:visible',
            'section[componentkey*="Topcard"] div[data-view-name="edge-creation-connect-action"] :is(a, button):visible',
            'section[componentkey*="Topcard"] div[data-view-name="relationship-building-button"] :is(a, button)[aria-label*="connect" i]:visible',
            'div[data-view-name="edge-creation-connect-action"] :is(a, button):visible',
            'div[data-view-name="relationship-building-button"] :is(a, button)[aria-label*="connect" i]:visible',
            'a[href*="/preload/custom-invite/"]:visible',
            'button[aria-label*="Invite"][aria-label*="connect" i]:visible',
            'a[aria-label*="Invite"][aria-label*="connect" i]:visible',
            'button:has-text("Connect"):visible',
            'a:has-text("Connect"):visible',
        ]

        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if not btn.is_visible(timeout=2000):
                    continue
                if self._is_connect_action(btn):
                    label = btn.get_attribute("aria-label") or ""
                    logger.info("Found Connect action via %s (%s)", sel, label)
                    return btn
                logger.debug("Matched non-connect action via %s", sel)
            except Exception:
                continue

        return None

    def _try_more_menu(self, page: object) -> object | None:
        """Click the '...' More button and look for Connect in the dropdown."""
        more_selectors = [
            'div[role="toolbar"] div[data-view-name="profile-overflow-button"] button:visible',
            'section[componentkey*="Topcard"] div[data-view-name="profile-overflow-button"] button:visible',
            'div[data-view-name="profile-overflow-button"] button:visible',
            "button[aria-label*='Open actions menu' i]:visible",
            "button[aria-label='More actions']:visible",
            "button[aria-label*='More actions' i]:visible",
            "button[aria-label='More']:visible",
            "button[aria-label*='More' i]:visible",
            "button:has(svg[id*='overflow']):visible",
        ]
        for sel in more_selectors:
            try:
                more_btn = page.locator(sel).first
                if more_btn.is_visible(timeout=2000):
                    logger.info("Opening More menu via: %s", sel)
                    more_btn.click(force=True)
                    _time.sleep(0.8)
                    # Now look for Connect in the dropdown
                    dropdown_selectors = [
                        "div.artdeco-dropdown__content-inner :is(button,a,div,li,span):has-text('Connect'):visible",
                        "div.artdeco-dropdown__content :is(button,a,div,li,span):has-text('Connect'):visible",
                        "[role='menu'] :is(button,a,div)[aria-label*='connect' i]:visible",
                        "[role='menu'] :is(button,a,div):has-text('Connect'):visible",
                        "button[role='menuitem']:has-text('Connect'):visible",
                        "div[role='menuitem']:has-text('Connect'):visible",
                        "li[role='menuitem']:has-text('Connect'):visible",
                        "li:has-text('Connect'):visible",
                    ]
                    for ds in dropdown_selectors:
                        try:
                            item = page.locator(ds).first
                            if item.is_visible(timeout=2000):
                                if self._is_connect_action(item):
                                    logger.info("Found Connect in More menu via: %s", ds)
                                    return item
                                logger.debug("Menu item matched but is not Connect: %s", ds)
                        except Exception:
                            continue
            except Exception:
                continue
        return None

    def _is_connect_action(self, el: object) -> bool:
        """Check if a located element looks like a real Connect CTA."""
        try:
            aria = el.get_attribute("aria-label") or ""
        except Exception:
            aria = ""
        try:
            href = el.get_attribute("href") or ""
        except Exception:
            href = ""
        text = self._safe_inner_text(el)
        return self._looks_like_connect_action(aria, text, href)

    def _safe_inner_text(self, el: object) -> str:
        try:
            text = el.inner_text(timeout=1000)
            if text:
                return text.strip()
        except Exception:
            pass
        try:
            text = el.text_content(timeout=1000)
            if text:
                return text.strip()
        except Exception:
            pass
        return ""

    def _looks_like_connect_action(self, aria_label: str | None, text: str | None, href: str | None) -> bool:
        """Return True when metadata indicates a connect/invite action."""
        aria = (aria_label or "").strip()
        text = (text or "").strip()
        href = (href or "").strip()
        blob = f"{aria} {text} {href}".lower()

        # Fast-path: invite URL used by LinkedIn connect flows.
        if "/preload/custom-invite/" in href.lower():
            return True

        # Explicit negative actions frequently present in profile headers.
        disallowed = (
            "pending",
            "follow",
            "unfollow",
            "message",
            "remove connection",
        )
        if any(token in blob for token in disallowed):
            return False

        if "invite" in blob and "connect" in blob:
            return True
        if text.lower() == "connect":
            return True
        if " connect" in blob or blob.startswith("connect"):
            # Avoid matching strings like "connections".
            return "connection" not in blob

        return False

    def _build_direct_invite_url(self, profile_url: str) -> str | None:
        """Build LinkedIn's direct invite URL from a profile URL when possible."""
        try:
            parsed = urlparse(profile_url)
            path = unquote(parsed.path or "")
            match = re.search(r"/in/([^/?#]+)/?", path, flags=re.IGNORECASE)
            if not match:
                return None
            vanity_name = match.group(1).strip()
            if not vanity_name:
                return None
            return f"https://www.linkedin.com/preload/custom-invite/?vanityName={quote(vanity_name)}"
        except Exception:
            return None

    def _handle_invite_page(self, page: object, note: str | None) -> bool:
        """Handle the /preload/custom-invite/ page that LinkedIn navigates to."""
        try:
            logger.info("On invite page: %s", page.url)
            self._human_delay(1.5, 3, "reading invite page")

            if note:
                # Look for the note/message textarea on the invite page
                try:
                    textarea = page.locator("textarea:visible").first
                    if textarea.is_visible(timeout=3000):
                        textarea.fill(note)
                        self._human_delay(0.5, 1.5, "typed note")
                except Exception:
                    logger.debug("No textarea found on invite page")

            self._human_delay(0.5, 1.5, "before send")

            # Look for Send / Send invitation button — could be <button> or <a>
            send_selectors = [
                "button[aria-label*='Send']:visible",
                "button:has-text('Send invitation'):visible",
                "button:has-text('Send without a note'):visible",
                "button:has-text('Send now'):visible",
                "button:has-text('Send'):visible",
                "a:has-text('Send'):visible",
            ]
            for sel in send_selectors:
                try:
                    send_btn = page.locator(sel).first
                    if send_btn.is_visible(timeout=2000):
                        logger.info("Clicking send via: %s", sel)
                        send_btn.click()
                        self._human_delay(2, 4, "after send click")
                        return True
                except Exception:
                    continue

            logger.warning("Could not find Send button on invite page")
            self._save_screenshot(page, "connect_fail_invite_page")
            self._save_html(page, "connect_fail_invite_page")
            return False
        except Exception:
            logger.exception("Error on invite page")
            return False

    def _handle_connect_modal(self, page: object, note: str | None) -> bool:
        """Handle the connection modal — optionally add a note, then send."""
        try:
            # Wait for the modal to actually appear
            modal = None
            modal_selectors = [
                "div[role='dialog']:visible",
                "div[class*='artdeco-modal']:visible",
                "div[data-test-modal]:visible",
            ]
            for sel in modal_selectors:
                try:
                    m = page.locator(sel).first
                    if m.is_visible(timeout=3000):
                        modal = m
                        logger.debug("Modal found via: %s", sel)
                        break
                except Exception:
                    continue

            if modal is None:
                logger.warning("No modal appeared after clicking Connect")
                return False

            # Pause to "read" the modal like a real person
            self._human_delay(1, 2.5, "reading modal")

            if note:
                # Look for "Add a note" button inside the modal
                try:
                    add_note = modal.locator("button:has-text('Add a note')").first
                    if add_note.is_visible(timeout=2000):
                        add_note.click()
                        self._human_delay(1, 2, "add note clicked")
                        textarea = modal.locator("textarea").first
                        if textarea.is_visible(timeout=2000):
                            textarea.fill(note)
                            self._human_delay(0.5, 1.5, "note typed")
                except Exception:
                    logger.debug("Could not add note — sending without one")

            # Small pause before hitting send
            self._human_delay(0.5, 1.5, "before send click")

            # Click Send — scoped to modal only to avoid clicking random page buttons
            send_selectors = [
                "button[aria-label='Send without a note']",
                "button[aria-label='Send now']",
                "button[aria-label='Send invitation']",
                "button:has-text('Send')",
            ]
            for sel in send_selectors:
                try:
                    send_btn = modal.locator(sel).first
                    if send_btn.is_visible(timeout=2000):
                        send_btn.click()
                        self._human_delay(1.5, 3, "after send click")
                        logger.debug("Clicked send via: %s", sel)
                        return True
                except Exception:
                    continue

            logger.warning("Could not find Send button in connect modal")
            return False
        except Exception:
            logger.exception("Error handling connect modal")
            return False

    def _has_invite_success_signal(self, page: object) -> bool:
        """Check for invite-page success states after sending."""
        success_selectors = [
            "text=Invitation sent",
            "text=Request sent",
            "text=You're connected",
            "text=Pending",
            "button:has-text('Pending'):visible",
            ":is(a, button)[aria-label*='Pending' i]:visible",
        ]
        for sel in success_selectors:
            try:
                if page.locator(sel).first.is_visible(timeout=1200):
                    logger.debug("Invite success signal via: %s", sel)
                    return True
            except Exception:
                continue
        return False

    def _invite_send_still_visible(self, page: object) -> bool:
        """True if invite-page send controls are still visible."""
        send_selectors = [
            "button[aria-label*='Send invitation' i]:visible",
            "button[aria-label='Send without a note']:visible",
            "button[aria-label='Send now']:visible",
            "button:has-text('Send invitation'):visible",
            "button:has-text('Send without a note'):visible",
            "button:has-text('Send now'):visible",
        ]
        for sel in send_selectors:
            try:
                if page.locator(sel).first.is_visible(timeout=800):
                    return True
            except Exception:
                continue
        return False

    def _verify_sent(self, page: object, profile_url: str) -> bool:
        """Verify the connection was actually sent by checking post-send state."""
        try:
            current_url = page.url
            logger.info("Verify: current URL is %s", current_url)

            # If we're no longer on the invite page, we likely got redirected
            # back to the profile — that's a good sign
            if "/custom-invite" not in current_url and "/preload/" not in current_url:
                # Back on the profile — check for Pending
                if self._is_already_connected(page):
                    return True
                # Check the main Connect button is gone
                main_connect = self._find_connect_button(page)
                if main_connect is None:
                    # Button is gone = sent
                    return True
                logger.debug("Main Connect button still visible — send likely failed")
                return False

            # Still on invite page — LinkedIn often lingers here with a loading spinner.
            # Wait briefly for the UI to settle before deciding.
            for _ in range(3):
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    pass
                self._human_delay(0.5, 1.0, "waiting invite verify settle")
                if self._has_invite_success_signal(page):
                    return True

            # If send controls disappeared on invite page, that's a positive signal.
            if not self._invite_send_still_visible(page):
                # LinkedIn sometimes keeps users on this URL with a spinner and no
                # explicit "Invitation sent" copy. If send controls are gone, treat
                # as success to avoid false negatives.
                if self._has_invite_success_signal(page):
                    return True
                logger.info("Verify: invite send controls disappeared; treating as sent")
                return True

            # Final fallback: reopen the profile and confirm Pending/connected state.
            try:
                logger.info("Verify fallback: opening profile to confirm state")
                page.goto(profile_url, wait_until="domcontentloaded")
                self._human_delay(1, 2, "waiting profile verify load")
                if self._is_already_connected(page):
                    return True
                # If Connect CTA is still visible on the profile, send likely failed.
                if self._find_connect_button(page) is not None:
                    logger.debug("Connect button still visible after profile reload")
                    return False
                # Conservative positive fallback: connect CTA gone.
                return True
            except Exception:
                logger.debug("Profile reload verification failed", exc_info=True)

            logger.debug("Could not confirm send — still on invite page")
            return False
        except Exception:
            logger.debug("Verification error", exc_info=True)
            return False
