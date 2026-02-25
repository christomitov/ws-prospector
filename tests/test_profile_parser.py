"""Tests for profile parser helpers."""

from scrapling.parser import Adaptor

from linkedin_leads.parsers.profile_parser import (
    parse_about_text,
    parse_detail_list_items,
    parse_profile_summary,
    parse_recent_posts,
)


def _page(html: str) -> Adaptor:
    return Adaptor(html, url="https://www.linkedin.com/in/test-user/")


def test_parse_profile_summary():
    page = _page(
        """
        <main>
          <section>
            <h1>Jane Doe</h1>
            <div class="text-body-medium">Head of Partnerships at Acme</div>
            <span class="text-body-small inline t-black--light break-words">Toronto, Ontario, Canada</span>
          </section>
        </main>
        """
    )
    summary = parse_profile_summary(page)
    assert summary["name"] == "Jane Doe"
    assert summary["headline"] == "Head of Partnerships at Acme"
    assert "Toronto" in (summary["location"] or "")


def test_parse_about_text_fallback_from_section_text():
    page = _page(
        """
        <main>
          <section>
            <h2>About</h2>
            <div>
              Builder-operator focused on scaling GTM teams globally.
            </div>
          </section>
        </main>
        """
    )
    about = parse_about_text(page)
    assert about is not None
    assert "Builder-operator" in about


def test_parse_detail_list_items():
    page = _page(
        """
        <main>
          <ul>
            <li class="pvs-list__paged-list-item">Senior Director, Partnerships · Acme · 2021 - Present</li>
            <li class="pvs-list__paged-list-item">Director, Partnerships · Acme · 2018 - 2021</li>
          </ul>
        </main>
        """
    )
    items = parse_detail_list_items(page)
    assert len(items) == 2
    assert "Senior Director" in items[0]


def test_parse_recent_posts():
    page = _page(
        """
        <main>
          <article>
            <a href="/feed/update/urn:li:activity:123">Post</a>
            <div>Excited to share our latest partnership launch.</div>
          </article>
        </main>
        """
    )
    posts = parse_recent_posts(page, max_items=3)
    assert len(posts) == 1
    assert posts[0]["url"] == "https://www.linkedin.com/feed/update/urn:li:activity:123"
    assert "latest partnership" in posts[0]["text"].lower()
