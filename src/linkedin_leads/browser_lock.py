"""Global async lock for browser profile access.

Only one Chromium instance can use a persistent profile directory at a time.
All browser operations (scraping, connect requests, session checks) must
acquire this lock before launching a browser.
"""

import asyncio

browser_lock = asyncio.Lock()
