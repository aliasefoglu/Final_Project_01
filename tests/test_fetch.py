"""Unit tests for src.services.fetch_service.

All HTTP is mocked with `respx` -- no network access, per the brief's
"all tests must run offline" requirement (S4.6).
"""

from __future__ import annotations

import httpx
import pytest
import respx

from src.services.fetch_service import HtmlScrapeSource, RssSource, fetch_all_sources

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Feed</title>
    <item>
      <title>Acme unveils new processor</title>
      <link>https://example.com/news/acme-chip?utm_source=rss</link>
      <description>Acme Corp announced a new processor today aimed at AI workloads.</description>
      <pubDate>Wed, 06 May 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Untitled malformed entry</title>
      <description>This entry has no link and must be skipped.</description>
    </item>
    <item>
      <link>https://example.com/news/no-title</link>
      <description>This entry has no title and must be skipped.</description>
    </item>
  </channel>
</rss>
"""

_LISTING_HTML = """
<html><body>
  <article><a href="/news/story-one">Story One</a></article>
  <article><a href="/news/story-two">Story Two</a></article>
</body></html>
"""

_ARTICLE_HTML = """
<html><head><title>Fallback Title</title></head>
<body>
  <h1>A Real Headline</h1>
  <p>First paragraph of the article body.</p>
  <p>Second paragraph with more detail.</p>
</body></html>
"""

_EMPTY_ARTICLE_HTML = "<html><body></body></html>"


@pytest.mark.asyncio
@respx.mock
async def test_rss_source_parses_valid_entries_and_skips_malformed() -> None:
    respx.get("https://feeds.example.com/rss.xml").mock(
        return_value=httpx.Response(200, text=_SAMPLE_RSS)
    )
    source = RssSource(feed_url="https://feeds.example.com/rss.xml", name="Example Feed")
    async with httpx.AsyncClient() as client:
        articles = await source.fetch(client)

    assert len(articles) == 1
    article = articles[0]
    assert article.title == "Acme unveils new processor"
    assert article.source == "Example Feed"
    assert "processor" in article.content


@pytest.mark.asyncio
@respx.mock
async def test_html_scrape_source_follows_links_and_extracts_articles() -> None:
    respx.get("https://news.example.com/").mock(return_value=httpx.Response(200, text=_LISTING_HTML))
    respx.get("https://news.example.com/news/story-one").mock(
        return_value=httpx.Response(200, text=_ARTICLE_HTML)
    )
    respx.get("https://news.example.com/news/story-two").mock(
        return_value=httpx.Response(200, text=_EMPTY_ARTICLE_HTML)
    )
    source = HtmlScrapeSource(listing_url="https://news.example.com/", name="Example Scrape")
    async with httpx.AsyncClient() as client:
        articles = await source.fetch(client)

    # story-two has no usable body and must be skipped; story-one must be kept.
    assert len(articles) == 1
    assert articles[0].title == "A Real Headline"
    assert articles[0].source == "Example Scrape"
    assert "First paragraph" in articles[0].content


@pytest.mark.asyncio
@respx.mock
async def test_fetch_all_sources_is_resilient_to_a_failing_source() -> None:
    respx.get("https://feeds.example.com/rss.xml").mock(
        return_value=httpx.Response(200, text=_SAMPLE_RSS)
    )
    respx.get("https://broken.example.com/rss.xml").mock(return_value=httpx.Response(500))

    good = RssSource(feed_url="https://feeds.example.com/rss.xml", name="Good Feed")
    bad = RssSource(feed_url="https://broken.example.com/rss.xml", name="Broken Feed")

    articles = await fetch_all_sources([good, bad], max_parallel=4)

    # The broken source is skipped after retries; the good source still
    # contributes its articles -- graceful degradation (brief S4.5).
    assert len(articles) == 1
    assert articles[0].source == "Good Feed"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_all_sources_runs_sources_concurrently() -> None:
    """One task raising must not prevent the others (and gather itself) from
    completing -- the required concurrency error-path test (brief S4.6)."""
    respx.get("https://a.example.com/rss.xml").mock(return_value=httpx.Response(200, text=_SAMPLE_RSS))
    respx.get("https://b.example.com/rss.xml").mock(return_value=httpx.Response(200, text=_SAMPLE_RSS))
    respx.get("https://c.example.com/rss.xml").mock(side_effect=httpx.ConnectError("boom"))

    sources = [
        RssSource(feed_url="https://a.example.com/rss.xml", name="A"),
        RssSource(feed_url="https://b.example.com/rss.xml", name="B"),
        RssSource(feed_url="https://c.example.com/rss.xml", name="C"),
    ]
    articles = await fetch_all_sources(sources, max_parallel=8)

    sources_seen = {a.source for a in articles}
    assert sources_seen == {"A", "B"}
