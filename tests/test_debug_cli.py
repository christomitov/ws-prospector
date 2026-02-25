"""Tests for CLI argument-mode validation."""

from argparse import Namespace

from linkedin_leads.debug import (
    _build_parser,
    _compact_record,
    _person_match_score,
    _resolve_collect_max_pages,
    validate_collect_mode,
)


def test_validate_collect_mode_rejects_sales_nav_query_mode():
    args = Namespace(query="ceo toronto", source="sales_navigator")
    ok, message = validate_collect_mode(args)
    assert not ok
    assert message is not None
    assert "--sales-url" in message


def test_validate_collect_mode_allows_linkedin_query_mode():
    args = Namespace(query="ceo toronto", source="linkedin_search")
    ok, message = validate_collect_mode(args)
    assert ok
    assert message is None


def test_validate_collect_mode_allows_sales_nav_url_mode():
    args = Namespace(query=None, source="sales_navigator")
    ok, message = validate_collect_mode(args)
    assert ok
    assert message is None


def test_collect_parser_accepts_stdout_json():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "collect",
            "--query",
            "example-prospect",
            "--stdout",
            "json",
        ]
    )
    assert args.stdout == "json"


def test_collect_parser_accepts_stdout_csv():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "collect",
            "--query",
            "example-prospect",
            "--stdout",
            "csv",
        ]
    )
    assert args.stdout == "csv"


def test_collect_parser_accepts_stdout_ndjson():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "collect",
            "--query",
            "example-prospect",
            "--stdout",
            "ndjson",
        ]
    )
    assert args.stdout == "ndjson"


def test_person_match_score_prefers_exact_name():
    exact = _person_match_score("Vriti Panwar", "Vriti Panwar, CIM®")
    partial = _person_match_score("Vriti Panwar", "Kapil Panwar")
    assert exact > partial


def test_collect_parser_accepts_person_query_flag():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "collect",
            "--query",
            "Vriti Panwar",
            "--person-query",
            "--stdout",
            "json",
        ]
    )
    assert args.person_query is True


def test_collect_parser_accepts_output_view_compact():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "collect",
            "--query",
            "Vriti Panwar",
            "--stdout",
            "json",
            "--output-view",
            "compact",
        ]
    )
    assert args.output_view == "compact"


def test_collect_parser_max_pages_defaults_to_auto_mode():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "collect",
            "--query",
            "Vriti Panwar",
            "--person-query",
        ]
    )
    assert args.max_pages is None


def test_resolve_collect_max_pages_defaults_to_one_for_person_query():
    args = Namespace(max_pages=None, person_query=True, query="Vriti Panwar")
    assert _resolve_collect_max_pages(args) == 1


def test_resolve_collect_max_pages_defaults_to_five_for_regular_query():
    args = Namespace(max_pages=None, person_query=False, query="founder")
    assert _resolve_collect_max_pages(args) == 5


def test_resolve_collect_max_pages_honors_explicit_value():
    args = Namespace(max_pages=3, person_query=True, query="Vriti Panwar")
    assert _resolve_collect_max_pages(args) == 3


def test_compact_record_shapes_profile_fields():
    record = {
        "run_id": 1,
        "collected_at": "2026-02-25T00:00:00Z",
        "lead": {
            "full_name": "Jane Doe",
            "linkedin_url": "https://www.linkedin.com/in/janedoe",
            "headline": "Founder at Acme",
            "current_title": "Founder",
            "current_company": "Acme",
            "location": "Toronto",
            "connection_degree": "2nd",
            "mutual_connections": 12,
        },
        "profile": {
            "profile_url": "https://www.linkedin.com/in/janedoe",
            "about": "Builder.",
            "experience_items": ["Founder · Acme · 2020 - Present"],
            "education_items": ["University of X"],
            "certifications_items": ["CFA"],
            "volunteering_items": ["Board Member"],
            "skills_items": ["Fundraising"],
            "honors_items": ["Top 40 Under 40"],
            "languages_items": ["English"],
            "featured_posts": [{"url": "https://www.linkedin.com/feed/update/urn:li:activity:1/", "text": "Post text"}],
            "activity_posts": [{"url": "https://www.linkedin.com/feed/update/urn:li:activity:2/", "text": "Activity text"}],
            "recent_posts": [],
            "errors": [],
        },
    }
    compact = _compact_record(record)
    assert compact["name"] == "Jane Doe"
    assert compact["linkedin_url"] == "https://www.linkedin.com/in/janedoe"
    assert compact["experience"] == ["Founder · Acme · 2020 - Present"]
    assert compact["featured_posts"][0]["url"].endswith("activity:1/")
