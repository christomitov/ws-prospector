"""SQLite persistence and export."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import date, datetime, timezone

from .config import DB_PATH, ensure_dirs
from .models import Lead, LeadSource

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key TEXT UNIQUE NOT NULL,
    linkedin_url TEXT,
    full_name TEXT NOT NULL,
    headline TEXT,
    current_title TEXT,
    current_company TEXT,
    location TEXT,
    connection_degree TEXT,
    mutual_connections INTEGER,
    source TEXT NOT NULL,
    search_query TEXT,
    scraped_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connect_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id),
    linkedin_url TEXT NOT NULL,
    full_name TEXT NOT NULL,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    scheduled_at TEXT,
    sent_at TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(linkedin_url)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);
CREATE INDEX IF NOT EXISTS idx_leads_company ON leads(current_company);
CREATE INDEX IF NOT EXISTS idx_leads_scraped_at ON leads(scraped_at);
CREATE INDEX IF NOT EXISTS idx_connect_status ON connect_queue(status);
CREATE INDEX IF NOT EXISTS idx_connect_scheduled ON connect_queue(scheduled_at);
"""

_UPSERT = """
INSERT INTO leads (dedup_key, linkedin_url, full_name, headline, current_title,
                   current_company, location, connection_degree, mutual_connections,
                   source, search_query, scraped_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(dedup_key) DO UPDATE SET
    headline = COALESCE(excluded.headline, leads.headline),
    current_title = COALESCE(excluded.current_title, leads.current_title),
    current_company = COALESCE(excluded.current_company, leads.current_company),
    location = COALESCE(excluded.location, leads.location),
    connection_degree = COALESCE(excluded.connection_degree, leads.connection_degree),
    mutual_connections = COALESCE(excluded.mutual_connections, leads.mutual_connections),
    scraped_at = excluded.scraped_at
"""

_COLUMNS = [
    "id", "dedup_key", "linkedin_url", "full_name", "headline", "current_title",
    "current_company", "location", "connection_degree", "mutual_connections",
    "source", "search_query", "scraped_at",
]


class LeadStore:
    def __init__(self, db_path: str | None = None) -> None:
        ensure_dirs()
        self._db_path = db_path or str(DB_PATH)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_CREATE_TABLE + _CREATE_INDEXES)

    def upsert(self, lead: Lead) -> None:
        with self._connect() as conn:
            conn.execute(_UPSERT, (
                lead.dedup_key,
                lead.linkedin_url,
                lead.full_name,
                lead.headline,
                lead.current_title,
                lead.current_company,
                lead.location,
                lead.connection_degree,
                lead.mutual_connections,
                lead.source.value,
                lead.search_query,
                lead.scraped_at.isoformat(),
            ))

    def upsert_many(self, leads: list[Lead]) -> int:
        count = 0
        with self._connect() as conn:
            for lead in leads:
                conn.execute(_UPSERT, (
                    lead.dedup_key,
                    lead.linkedin_url,
                    lead.full_name,
                    lead.headline,
                    lead.current_title,
                    lead.current_company,
                    lead.location,
                    lead.connection_degree,
                    lead.mutual_connections,
                    lead.source.value,
                    lead.search_query,
                    lead.scraped_at.isoformat(),
                ))
                count += 1
        return count

    def query(
        self,
        source: LeadSource | None = None,
        company: str | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[str | int] = []
        if source:
            clauses.append("source = ?")
            params.append(source.value)
        if company:
            clauses.append("current_company LIKE ?")
            params.append(f"%{company}%")
        if search:
            clauses.append("(full_name LIKE ? OR headline LIKE ? OR current_title LIKE ?)")
            params.extend([f"%{search}%"] * 3)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM leads {where} ORDER BY scraped_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def count(self, source: LeadSource | None = None) -> int:
        if source:
            sql = "SELECT COUNT(*) FROM leads WHERE source = ?"
            params: tuple = (source.value,)
        else:
            sql = "SELECT COUNT(*) FROM leads"
            params = ()
        with self._connect() as conn:
            return conn.execute(sql, params).fetchone()[0]

    def stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            by_source = {}
            for src in LeadSource:
                c = conn.execute(
                    "SELECT COUNT(*) FROM leads WHERE source = ?", (src.value,)
                ).fetchone()[0]
                by_source[src.value] = c
            recent = conn.execute(
                "SELECT scraped_at FROM leads ORDER BY scraped_at DESC LIMIT 1"
            ).fetchone()
        return {
            "total": total,
            "by_source": by_source,
            "last_scraped": recent[0] if recent else None,
        }

    def export_csv(self, source: LeadSource | None = None) -> str:
        rows = self.query(source=source, limit=100_000)
        output = io.StringIO()
        if not rows:
            return ""
        writer = csv.DictWriter(output, fieldnames=[c for c in _COLUMNS if c != "dedup_key"])
        writer.writeheader()
        for row in rows:
            row.pop("dedup_key", None)
            writer.writerow(row)
        return output.getvalue()

    def export_json(self, source: LeadSource | None = None) -> str:
        rows = self.query(source=source, limit=100_000)
        for row in rows:
            row.pop("dedup_key", None)
        return json.dumps(rows, indent=2, default=str)

    def clear_leads(self) -> dict:
        """Delete all leads and related connect queue rows."""
        with self._connect() as conn:
            leads_deleted = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            queue_deleted = conn.execute("SELECT COUNT(*) FROM connect_queue").fetchone()[0]
            conn.execute("DELETE FROM connect_queue")
            conn.execute("DELETE FROM leads")
        return {"leads_deleted": leads_deleted, "queue_deleted": queue_deleted}

    # ── Connect Queue ─────────────────────────────────────────────────────

    def enqueue_connects(self, lead_ids: list[int], note: str | None = None) -> int:
        """Add leads to the connect request queue.

        Returns the number of rows newly queued:
        - new insert, or
        - existing failed row reset back to pending.
        """
        now = datetime.now(timezone.utc).isoformat()
        added = 0
        with self._connect() as conn:
            for lid in lead_ids:
                row = conn.execute(
                    "SELECT id, linkedin_url, full_name FROM leads WHERE id = ?", (lid,)
                ).fetchone()
                if not row or not row["linkedin_url"]:
                    continue
                try:
                    cur = conn.execute(
                        """INSERT OR IGNORE INTO connect_queue
                           (lead_id, linkedin_url, full_name, note, status, created_at)
                           VALUES (?, ?, ?, ?, 'pending', ?)""",
                        (row["id"], row["linkedin_url"], row["full_name"], note, now),
                    )

                    # Fresh insert.
                    if cur.rowcount == 1:
                        added += 1
                        continue

                    # Duplicate URL already in queue. If it previously failed,
                    # reset it so users can retry after selector/session issues.
                    existing = conn.execute(
                        "SELECT id, status FROM connect_queue WHERE linkedin_url = ?",
                        (row["linkedin_url"],),
                    ).fetchone()
                    if existing and existing["status"] == "failed":
                        conn.execute(
                            """UPDATE connect_queue
                               SET lead_id = ?, full_name = ?, note = ?, status = 'pending',
                                   scheduled_at = NULL, sent_at = NULL, error = NULL, created_at = ?
                               WHERE id = ?""",
                            (row["id"], row["full_name"], note, now, existing["id"]),
                        )
                        added += 1
                except sqlite3.IntegrityError:
                    pass
        return added

    def next_pending_connect(self) -> dict | None:
        """Get the next pending connect request."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM connect_queue WHERE status = 'pending' ORDER BY id LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def mark_connect(self, queue_id: int, status: str, error: str | None = None) -> None:
        """Mark a connect request as sent or failed."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE connect_queue SET status = ?, sent_at = ?, error = ? WHERE id = ?",
                (status, now if status == "sent" else None, error, queue_id),
            )

    def connect_queue_stats(self) -> dict:
        with self._connect() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) FROM connect_queue WHERE status = 'pending'"
            ).fetchone()[0]
            sent = conn.execute(
                "SELECT COUNT(*) FROM connect_queue WHERE status = 'sent'"
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM connect_queue WHERE status = 'failed'"
            ).fetchone()[0]
        return {"pending": pending, "sent": sent, "failed": failed}

    def connect_queue_list(self, status: str | None = None, limit: int = 100) -> list[dict]:
        if status:
            sql = "SELECT * FROM connect_queue WHERE status = ? ORDER BY id LIMIT ?"
            params: tuple = (status, limit)
        else:
            sql = "SELECT * FROM connect_queue ORDER BY id LIMIT ?"
            params = (limit,)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def connect_sent_count_for_local_day(self, target_day: date | None = None) -> int:
        """Count sent connect requests whose sent_at falls on the local calendar day."""
        day = target_day or datetime.now().astimezone().date()
        count = 0
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT sent_at FROM connect_queue WHERE status = 'sent' AND sent_at IS NOT NULL"
            ).fetchall()
        for row in rows:
            raw = row["sent_at"]
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(raw)
            except Exception:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt.astimezone().date() == day:
                count += 1
        return count

    # ── App Settings ─────────────────────────────────────────────────────

    def get_json_setting(self, key: str, default: dict | None = None) -> dict:
        fallback = default or {}
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
        if not row:
            return fallback
        raw = row["value"]
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else fallback
        except Exception:
            return fallback

    def set_json_setting(self, key: str, value: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(value)
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO app_settings (key, value, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                     value = excluded.value,
                     updated_at = excluded.updated_at""",
                (key, payload, now),
            )

    def get_connect_settings(self) -> dict:
        return self.get_json_setting("connect_settings", default={})

    def save_connect_settings(self, settings: dict) -> None:
        self.set_json_setting("connect_settings", settings)
