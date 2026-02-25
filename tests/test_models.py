"""Tests for the Lead model."""

from datetime import datetime, timezone

from linkedin_leads.models import Lead, LeadSource


def test_lead_url_normalization():
    lead = Lead(
        linkedin_url="https://linkedin.com/in/john-doe/?utm=test",
        full_name="John Doe",
        source=LeadSource.linkedin_search,
    )
    assert lead.linkedin_url == "https://www.linkedin.com/in/john-doe"


def test_lead_url_normalization_www():
    lead = Lead(
        linkedin_url="http://www.linkedin.com/in/jane-smith/",
        full_name="Jane Smith",
        source=LeadSource.linkedin_search,
    )
    assert lead.linkedin_url == "https://www.linkedin.com/in/jane-smith"


def test_lead_url_none():
    lead = Lead(
        full_name="No URL Person",
        source=LeadSource.company_employees,
    )
    assert lead.linkedin_url is None


def test_dedup_key_uses_url():
    lead = Lead(
        linkedin_url="https://www.linkedin.com/in/john-doe",
        full_name="John Doe",
        source=LeadSource.linkedin_search,
    )
    assert lead.dedup_key == "https://www.linkedin.com/in/john-doe"


def test_dedup_key_fallback_name_company():
    lead = Lead(
        full_name="John Doe",
        current_company="Acme Inc",
        source=LeadSource.linkedin_search,
    )
    assert lead.dedup_key == "John Doe|Acme Inc"


def test_dedup_key_fallback_no_company():
    lead = Lead(
        full_name="John Doe",
        source=LeadSource.linkedin_search,
    )
    assert lead.dedup_key == "John Doe|"


def test_lead_default_scraped_at():
    lead = Lead(full_name="Test", source=LeadSource.linkedin_search)
    assert isinstance(lead.scraped_at, datetime)
    assert lead.scraped_at.tzinfo is not None


def test_lead_all_fields():
    lead = Lead(
        linkedin_url="https://www.linkedin.com/in/test-user",
        full_name="Test User",
        headline="Engineer at Startup",
        current_title="Engineer",
        current_company="Startup",
        location="San Francisco, CA",
        connection_degree="2nd",
        mutual_connections=5,
        source=LeadSource.sales_navigator,
        search_query="engineer startup",
    )
    assert lead.full_name == "Test User"
    assert lead.source == LeadSource.sales_navigator
    assert lead.mutual_connections == 5
