"""Tests for the LeadStore."""

from datetime import datetime, time, timedelta, timezone

import pytest

from linkedin_leads.models import Lead, LeadSource
from linkedin_leads.storage import LeadStore


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_leads.db")
    return LeadStore(db_path=db_path)


def _make_lead(name="John Doe", url="https://www.linkedin.com/in/john-doe", **kw):
    defaults = dict(
        linkedin_url=url,
        full_name=name,
        headline="Engineer at Acme",
        current_title="Engineer",
        current_company="Acme",
        location="SF",
        source=LeadSource.linkedin_search,
        search_query="engineer",
    )
    defaults.update(kw)
    return Lead(**defaults)


def test_upsert_and_query(store):
    lead = _make_lead()
    store.upsert(lead)
    rows = store.query()
    assert len(rows) == 1
    assert rows[0]["full_name"] == "John Doe"


def test_upsert_deduplicates(store):
    lead1 = _make_lead(headline="Engineer at Acme")
    lead2 = _make_lead(headline="Senior Engineer at Acme")
    store.upsert(lead1)
    store.upsert(lead2)
    rows = store.query()
    assert len(rows) == 1
    assert rows[0]["headline"] == "Senior Engineer at Acme"


def test_upsert_many(store):
    leads = [
        _make_lead(name="Alice", url="https://www.linkedin.com/in/alice"),
        _make_lead(name="Bob", url="https://www.linkedin.com/in/bob"),
        _make_lead(name="Charlie", url="https://www.linkedin.com/in/charlie"),
    ]
    count = store.upsert_many(leads)
    assert count == 3
    assert store.count() == 3


def test_query_filter_source(store):
    store.upsert(_make_lead(name="A", url="https://www.linkedin.com/in/a", source=LeadSource.linkedin_search))
    store.upsert(_make_lead(name="B", url="https://www.linkedin.com/in/b", source=LeadSource.sales_navigator))
    rows = store.query(source=LeadSource.linkedin_search)
    assert len(rows) == 1
    assert rows[0]["full_name"] == "A"


def test_query_filter_company(store):
    store.upsert(_make_lead(name="A", url="https://www.linkedin.com/in/a", current_company="Google"))
    store.upsert(_make_lead(name="B", url="https://www.linkedin.com/in/b", current_company="Meta"))
    rows = store.query(company="Google")
    assert len(rows) == 1


def test_query_filter_search(store):
    store.upsert(_make_lead(name="Alice Smith", url="https://www.linkedin.com/in/alice"))
    store.upsert(_make_lead(name="Bob Jones", url="https://www.linkedin.com/in/bob"))
    rows = store.query(search="Alice")
    assert len(rows) == 1


def test_count(store):
    store.upsert(_make_lead(name="A", url="https://www.linkedin.com/in/a"))
    store.upsert(_make_lead(name="B", url="https://www.linkedin.com/in/b"))
    assert store.count() == 2


def test_count_by_source(store):
    store.upsert(_make_lead(name="A", url="https://www.linkedin.com/in/a", source=LeadSource.linkedin_search))
    store.upsert(_make_lead(name="B", url="https://www.linkedin.com/in/b", source=LeadSource.company_employees))
    assert store.count(source=LeadSource.linkedin_search) == 1
    assert store.count(source=LeadSource.company_employees) == 1


def test_stats(store):
    store.upsert(_make_lead(name="A", url="https://www.linkedin.com/in/a"))
    s = store.stats()
    assert s["total"] == 1
    assert s["by_source"]["linkedin_search"] == 1
    assert s["last_scraped"] is not None


def test_export_csv(store):
    store.upsert(_make_lead())
    csv_data = store.export_csv()
    assert "John Doe" in csv_data
    assert "linkedin_url" in csv_data  # header present


def test_export_json(store):
    store.upsert(_make_lead())
    json_data = store.export_json()
    assert "John Doe" in json_data


def test_export_empty(store):
    assert store.export_csv() == ""
    assert store.export_json() == "[]"


def test_pagination(store):
    for i in range(10):
        store.upsert(_make_lead(name=f"User {i}", url=f"https://www.linkedin.com/in/user-{i}"))
    page1 = store.query(limit=3, offset=0)
    page2 = store.query(limit=3, offset=3)
    assert len(page1) == 3
    assert len(page2) == 3
    assert page1[0]["full_name"] != page2[0]["full_name"]


def test_enqueue_connects_counts_only_new_or_reset(store):
    store.upsert(_make_lead(name="Queue User", url="https://www.linkedin.com/in/queue-user"))
    lead_id = store.query(limit=1)[0]["id"]

    assert store.enqueue_connects([lead_id]) == 1
    # Duplicate pending row should not be counted again.
    assert store.enqueue_connects([lead_id]) == 0


def test_enqueue_connects_requeues_failed_item(store):
    store.upsert(_make_lead(name="Retry User", url="https://www.linkedin.com/in/retry-user"))
    lead_id = store.query(limit=1)[0]["id"]

    assert store.enqueue_connects([lead_id]) == 1
    queue_item = store.next_pending_connect()
    assert queue_item is not None

    store.mark_connect(queue_item["id"], "failed", error="temporary selector issue")
    failed_rows = store.connect_queue_list(status="failed")
    assert len(failed_rows) == 1

    # Re-enqueue should reset failed row back to pending and count as added.
    assert store.enqueue_connects([lead_id]) == 1
    pending_rows = store.connect_queue_list(status="pending")
    assert len(pending_rows) == 1
    assert pending_rows[0]["error"] is None


def test_connect_sent_count_for_local_day(store):
    now_local = datetime.now().astimezone()
    today = now_local.date()
    yesterday = today - timedelta(days=1)
    local_tz = now_local.tzinfo
    assert local_tz is not None

    today_iso = datetime.combine(today, time(12, 0), tzinfo=local_tz).astimezone(timezone.utc).isoformat()
    yesterday_iso = datetime.combine(yesterday, time(12, 0), tzinfo=local_tz).astimezone(timezone.utc).isoformat()

    with store._connect() as conn:
        conn.execute(
            """INSERT INTO connect_queue
               (lead_id, linkedin_url, full_name, note, status, created_at, sent_at)
               VALUES (1, ?, ?, NULL, 'sent', ?, ?)""",
            ("https://www.linkedin.com/in/sent-today", "Sent Today", today_iso, today_iso),
        )
        conn.execute(
            """INSERT INTO connect_queue
               (lead_id, linkedin_url, full_name, note, status, created_at, sent_at)
               VALUES (2, ?, ?, NULL, 'sent', ?, ?)""",
            ("https://www.linkedin.com/in/sent-yesterday", "Sent Yesterday", yesterday_iso, yesterday_iso),
        )
        conn.execute(
            """INSERT INTO connect_queue
               (lead_id, linkedin_url, full_name, note, status, created_at, sent_at)
               VALUES (3, ?, ?, NULL, 'pending', ?, NULL)""",
            ("https://www.linkedin.com/in/pending-only", "Pending Only", today_iso),
        )

    assert store.connect_sent_count_for_local_day(today) == 1
    assert store.connect_sent_count_for_local_day(yesterday) == 1
