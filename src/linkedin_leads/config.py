"""Paths and default settings."""

import os
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "wealthsimple-prospector"
LEGACY_APP_NAME = "linkedin-leads"

# Prefer the new app dir, but keep using legacy data automatically if it
# already exists and the new dir has not been created yet.
_new_data_dir = Path(user_data_dir(APP_NAME))
_legacy_data_dir = Path(user_data_dir(LEGACY_APP_NAME))
DATA_DIR = _legacy_data_dir if (_legacy_data_dir.exists() and not _new_data_dir.exists()) else _new_data_dir
SESSIONS_DIR = DATA_DIR / "sessions"
DB_PATH = DATA_DIR / "leads.db"
CRAWL_DIR = DATA_DIR / "crawldata"
LOG_DIR = DATA_DIR / "logs"
LOG_FILE = LOG_DIR / "server.log"
try:
    LOG_RETENTION_DAYS = max(1, int(os.getenv("WSP_LOG_RETENTION_DAYS", "14")))
except ValueError:
    LOG_RETENTION_DAYS = 14

# Rate-limit defaults (seconds)
DEFAULT_DELAY = 3.0
SALES_NAV_DELAY = 4.0
BLOCK_WAIT = 30.0
MAX_RETRIES = 2

# Server
HOST = "127.0.0.1"
PORT = 8000


def ensure_dirs() -> None:
    """Create required directories on first run."""
    for d in (DATA_DIR, SESSIONS_DIR, CRAWL_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
