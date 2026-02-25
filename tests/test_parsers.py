"""Tests for parser utility functions."""

from scrapling.parser import Adaptor

from linkedin_leads.models import LeadSource
from linkedin_leads.parsers.navigator_parser import parse_navigator_results
from linkedin_leads.parsers.common import (
    clean_text,
    extract_connection_degree,
    extract_mutual_count,
    normalize_linkedin_url,
    split_title_company,
)


class TestCleanText:
    def test_basic_strip(self):
        assert clean_text("  hello world  ") == "hello world"

    def test_collapse_whitespace(self):
        assert clean_text("hello   \n\t  world") == "hello world"

    def test_remove_zero_width(self):
        assert clean_text("hel\u200blo") == "hello"

    def test_none_input(self):
        assert clean_text(None) is None

    def test_empty_string(self):
        assert clean_text("") is None

    def test_only_whitespace(self):
        assert clean_text("   ") is None


class TestNormalizeLinkedinUrl:
    def test_strips_query_params(self):
        assert normalize_linkedin_url(
            "https://www.linkedin.com/in/john-doe?miniProfileUrn=123"
        ) == "https://www.linkedin.com/in/john-doe"

    def test_strips_trailing_slash(self):
        assert normalize_linkedin_url(
            "https://www.linkedin.com/in/john-doe/"
        ) == "https://www.linkedin.com/in/john-doe"

    def test_normalizes_http(self):
        assert normalize_linkedin_url(
            "http://linkedin.com/in/john-doe"
        ) == "https://www.linkedin.com/in/john-doe"

    def test_none_input(self):
        assert normalize_linkedin_url(None) is None

    def test_invalid_url(self):
        assert normalize_linkedin_url("https://www.linkedin.com/company/acme") is None

    def test_sales_lead_url(self):
        url = "https://www.linkedin.com/sales/lead/ACwAA123"
        assert normalize_linkedin_url(url) == url

    def test_relative_sales_lead_url(self):
        assert normalize_linkedin_url("/sales/lead/ACwAA123?_ntb=abc") == "https://www.linkedin.com/sales/lead/ACwAA123"

    def test_relative_profile_url(self):
        assert normalize_linkedin_url("/in/john-doe/") == "https://www.linkedin.com/in/john-doe"


class TestExtractConnectionDegree:
    def test_1st(self):
        assert extract_connection_degree("1st") == "1st"

    def test_2nd(self):
        assert extract_connection_degree("2nd degree connection") == "2nd"

    def test_3rd(self):
        assert extract_connection_degree("· 3rd") == "3rd"

    def test_none_input(self):
        assert extract_connection_degree(None) is None

    def test_no_match(self):
        assert extract_connection_degree("no degree here") is None


class TestExtractMutualCount:
    def test_basic(self):
        assert extract_mutual_count("23 mutual connections") == 23

    def test_single(self):
        assert extract_mutual_count("1 mutual connection") == 1

    def test_with_other(self):
        assert extract_mutual_count("16 other mutual connections") == 16

    def test_none_input(self):
        assert extract_mutual_count(None) is None

    def test_no_match(self):
        assert extract_mutual_count("no connections") is None


class TestSplitTitleCompany:
    def test_at_separator(self):
        assert split_title_company("Engineer at Google") == ("Engineer", "Google")

    def test_dash_separator(self):
        assert split_title_company("CTO - Startup Inc") == ("CTO", "Startup Inc")

    def test_pipe_separator(self):
        assert split_title_company("VP Sales | Acme Corp") == ("VP Sales", "Acme Corp")

    def test_at_sign_separator(self):
        assert split_title_company("Dev @ Meta") == ("Dev", "Meta")

    def test_no_separator(self):
        assert split_title_company("Software Engineer") == ("Software Engineer", None)

    def test_none_input(self):
        assert split_title_company(None) == (None, None)


class TestParseNavigatorResults:
    def test_parses_modern_sales_nav_card(self):
        html = """
        <div data-x-search-result="LEAD">
          <a data-lead-search-result="profile-link-st1" href="/sales/lead/ACwAAAAA,NAME_SEARCH,abcd?_ntb=xyz">
            <span data-anonymize="person-name">Jane Doe</span>
          </a>
          <span class="artdeco-entity-lockup__degree">· 2nd</span>
          <span data-anonymize="title">Founder</span>
          <a data-anonymize="company-name">Acme Inc</a>
          <span data-anonymize="location">Toronto, Ontario, Canada</span>
          <button>11 mutual connections</button>
        </div>
        """
        leads = parse_navigator_results(Adaptor(html), search_query="sales-nav-board")
        assert len(leads) == 1

        lead = leads[0]
        assert lead.full_name == "Jane Doe"
        assert lead.current_title == "Founder"
        assert lead.current_company == "Acme Inc"
        assert lead.location == "Toronto, Ontario, Canada"
        assert lead.connection_degree == "2nd"
        assert lead.mutual_connections == 11
        assert lead.linkedin_url == "https://www.linkedin.com/sales/lead/ACwAAAAA,NAME_SEARCH,abcd"
        assert lead.source == LeadSource.sales_navigator
        assert lead.search_query == "sales-nav-board"
