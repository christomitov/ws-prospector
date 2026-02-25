"""Tests for profile parser helpers."""

from scrapling.parser import Adaptor

from linkedin_leads.parsers.profile_parser import (
    parse_activity_posts,
    parse_about_text,
    parse_detail_list_items,
    parse_featured_posts,
    parse_profile_section_items,
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


def test_parse_detail_list_items_hydration_fallback():
    page = _page(
        """
        <main>
          <script>
            const boot = {"cacheKey":"profile_ExperienceDetailsSection_test-user","items":["Founder at Acme 2020 - Present","Advisor at Beta 2018 - 2020"]};
          </script>
        </main>
        """
    )
    items = parse_detail_list_items(page, section_hint="experience")
    assert len(items) >= 1
    assert "Acme" in items[0]


def test_parse_profile_section_items_from_main_profile():
    page = _page(
        """
        <main>
          <section>
            <div id="experience"></div>
            <ul>
              <li>CEO at Acme · 2021 - Present</li>
              <li>COO at Beta · 2017 - 2021</li>
            </ul>
          </section>
        </main>
        """
    )
    items = parse_profile_section_items(page, section_hint="experience", max_items=5)
    assert len(items) == 2
    assert "CEO at Acme" in items[0]


def test_parse_profile_section_items_from_paragraph_sections():
    page = _page(
        """
        <main>
          <section>
            <h2>Education</h2>
            <p>Queen's University</p>
            <p>Bachelor of Arts (Honours), Applied Economics & Mathematics</p>
            <p>Major in Applied Economics and minor in Mathematics</p>
          </section>
          <section>
            <h2>Licenses & certifications</h2>
            <p>Chartered Investment Manager (CIM®)</p>
            <p>Canadian Securities Institute</p>
            <p>Issued Aug 2025 · Expires Aug 2026</p>
          </section>
          <section>
            <h2>Volunteering</h2>
            <p>Treasurer, Board of Directors</p>
            <p>The Reading Partnership</p>
            <p>Jun 2025 - Present · 9 mos</p>
          </section>
        </main>
        """
    )
    education = parse_profile_section_items(page, section_hint="education", max_items=8)
    certifications = parse_profile_section_items(page, section_hint="certifications", max_items=8)
    volunteering = parse_profile_section_items(page, section_hint="volunteering", max_items=8)
    assert any("Queen's University" in row for row in education)
    assert any("Chartered Investment Manager" in row for row in certifications)
    assert any("Treasurer, Board of Directors" in row for row in volunteering)


def test_parse_featured_posts():
    page = _page(
        """
        <main>
          <section>
            <h2>Featured</h2>
            <a href="/feed/update/urn:li:activity:111">
              Post Building in public with better client outcomes.
            </a>
          </section>
        </main>
        """
    )
    posts = parse_featured_posts(page, max_items=3)
    assert len(posts) == 1
    assert posts[0]["url"] == "https://www.linkedin.com/feed/update/urn:li:activity:111"
    assert "building in public" in posts[0]["text"].lower()


def test_parse_activity_posts():
    page = _page(
        """
        <main>
          <section>
            <h2>Activity</h2>
            <div>Posts</div>
            <a href="/feed/update/urn:li:activity:222">
              Post Helping founders navigate liquidity events.
            </a>
          </section>
        </main>
        """
    )
    posts = parse_activity_posts(page, max_items=3)
    assert len(posts) == 1
    assert posts[0]["url"] == "https://www.linkedin.com/feed/update/urn:li:activity:222"
    assert "liquidity events" in posts[0]["text"].lower()


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
