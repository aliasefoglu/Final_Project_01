"""Concurrent, source-agnostic article ingestion.

Two source types are provided, both implementing the `NewsSource`
interface -- the same abstract-provider pattern the `ai` package uses for
`LLMProvider` (TOPIC.md's recommended OOP example):

- `RssSource`        : parses an RSS/Atom feed with `feedparser`.
- `HtmlScrapeSource` : fetches a listing page, follows article links, and
                       scrapes each one with BeautifulSoup. Satisfies the
                       "at least one direct-scraped HTML source" requirement.

Both are fetched through one shared `httpx.AsyncClient`, orchestrated by
`fetch_all_sources`, which bounds concurrency with an `asyncio.Semaphore`
and isolates failures per source so a single broken feed never aborts the
whole ingestion run (graceful degradation, brief S4.5).
"""

from __future__ import annotations

import abc
import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import settings
from src.models import Article

logger = logging.getLogger(__name__)

# Transient failures worth retrying. 4xx (other than 429) are not included:
# retrying a malformed request just wastes time and quota.
_TRANSIENT_EXC = (httpx.TransportError, httpx.HTTPStatusError)


def _make_article_id(url: str) -> str:
    """Deterministic id from the (pre-canonicalization) URL.

    Deterministic (not random) so re-fetching the same article between
    runs is idempotent at the id level too, not just via content_hash.
    """
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def _parse_struct_time(struct_time) -> datetime:
    if struct_time is None:
        return datetime.now(timezone.utc)

    try:
        return datetime(
            year=struct_time.tm_year,
            month=struct_time.tm_mon,
            day=struct_time.tm_mday,
            hour=struct_time.tm_hour,
            minute=struct_time.tm_min,
            second=struct_time.tm_sec,
            tzinfo=timezone.utc,
        )
    except (AttributeError, TypeError, ValueError):
        return datetime.now(timezone.utc)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
    retry=retry_if_exception_type(_TRANSIENT_EXC),
)
async def _get(client: httpx.AsyncClient, url: str, *, timeout: float) -> httpx.Response:
    """A single retried, timed-out GET. Raises on non-2xx after retries."""
    response = await client.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response


class NewsSource(abc.ABC):
    """Contract for a single, named source of articles.

    Subclasses implement only `fetch`; retries, timeouts, concurrency
    bounding, and per-source error isolation all live in
    `fetch_all_sources`, so individual sources stay simple and unit-testable
    in isolation.
    """

    name: str

    @abc.abstractmethod
    async def fetch(self, client: httpx.AsyncClient) -> list[Article]:
        """Return the articles currently available from this source."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"


@dataclass
class RssSource(NewsSource):
    """Fetches and parses a single RSS/Atom feed."""

    feed_url: str
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.feed_url

    async def fetch(self, client: httpx.AsyncClient) -> list[Article]:
        response = await _get(client, self.feed_url, timeout=settings.fetch_timeout_seconds)
        parsed = feedparser.parse(response.content)
        articles = [a for a in (self._entry_to_article(e) for e in parsed.entries) if a is not None]
        logger.info(
            "RssSource(%s): parsed %d entries, %d valid",
            self.name, len(parsed.entries), len(articles),
        )
        return articles

    def _entry_to_article(self, entry) -> Article | None:
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", None)
        if not link or not title:
            logger.debug("RssSource(%s): skipping malformed entry (missing link/title)", self.name)
            return None
        raw_content = getattr(entry, "summary", None) or getattr(entry, "description", None) or ""
        content = BeautifulSoup(raw_content, "html.parser").get_text(" ", strip=True)
        if not content.strip():
            logger.debug("RssSource(%s): skipping entry with empty body: %s", self.name, link)
            return None
        return Article(
            id=_make_article_id(link),
            title=title.strip(),
            content=content,
            url=link,
            source=self.name,
            published_at=_parse_struct_time(getattr(entry, "published_parsed", None)),
        )


@dataclass
class HtmlScrapeSource(NewsSource):
    """Direct-scrapes a listing page for article links, then scrapes each one.

    Intentionally simple (no JS rendering, no pagination) -- it demonstrates
    the scraping pattern required by the brief rather than aiming to be a
    general-purpose crawler. Each broken article page is skipped
    individually so one bad link doesn't sink the whole source.
    """

    listing_url: str
    name: str = ""
    link_selector: str = "a[href]"
    max_articles: int = 10

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.listing_url

    async def fetch(self, client: httpx.AsyncClient) -> list[Article]:
        response = await _get(client, self.listing_url, timeout=settings.fetch_timeout_seconds)
        soup = BeautifulSoup(response.text, "html.parser")
        links = self._extract_article_links(soup)

        articles: list[Article] = []
        for link in links[: self.max_articles]:
            try:
                article = await self._scrape_article(client, link)
            except _TRANSIENT_EXC as exc:
                logger.warning("HtmlScrapeSource(%s): failed to scrape %s: %s", self.name, link, exc)
                continue
            if article is not None:
                articles.append(article)
        logger.info("HtmlScrapeSource(%s): scraped %d/%d candidate links", self.name, len(articles), len(links))
        return articles

    def _extract_article_links(self, soup: BeautifulSoup) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for tag in soup.select(self.link_selector):
            href = tag.get("href")
            if not href:
                continue
            absolute = str(httpx.URL(self.listing_url).join(href))
            if absolute not in seen and absolute.startswith(("http://", "https://")):
                seen.add(absolute)
                out.append(absolute)
        return out

    async def _scrape_article(self, client: httpx.AsyncClient, url: str) -> Article | None:
        response = await _get(client, url, timeout=settings.fetch_timeout_seconds)
        soup = BeautifulSoup(response.text, "html.parser")
        title_tag = soup.find("h1") or soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else None
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        content = "\n".join(p for p in paragraphs if p)
        if not title or not content.strip():
            logger.debug("HtmlScrapeSource(%s): skipping page with no title/body: %s", self.name, url)
            return None
        return Article(
            id=_make_article_id(url),
            title=title,
            content=content,
            url=url,
            source=self.name,
            published_at=datetime.now(timezone.utc),
            raw_html=response.text,
        )


async def fetch_all_sources(
    sources: list[NewsSource],
    *,
    max_parallel: int | None = None,
) -> list[Article]:
    """Fetch every source concurrently, bounded by a semaphore.

    A source that raises (after its own internal retries are exhausted) is
    logged and skipped -- one broken feed never aborts the whole ingestion
    run.
    """
    limit = max_parallel or settings.max_parallel_fetches
    semaphore = asyncio.Semaphore(limit)
    timeout = httpx.Timeout(settings.fetch_timeout_seconds)

    async def _bounded_fetch(client: httpx.AsyncClient, source: NewsSource) -> list[Article]:
        async with semaphore:
            try:
                return await source.fetch(client)
            except Exception:
                logger.exception("Source %r failed after retries; continuing without it.", source)
                return []

    async with httpx.AsyncClient(
        headers={"User-Agent": "newsbrief/1.0 (+AI-ENG-110 course project)"},
        timeout=timeout,
    ) as client:
        results = await asyncio.gather(*(_bounded_fetch(client, s) for s in sources))

    return [article for batch in results for article in batch]
