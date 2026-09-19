from __future__ import annotations
import asyncio
import json
import logging
import time
from pathlib import Path
from urllib.parse import urlparse
from ai.dedup import url_canonicalize
from src.config import settings
from src.core.dedup import Deduplicator
from src.core.digest_builder import DigestItem, render_markdown, write_digest
from src.models import User
from src.services.ai_service import AIService
from src.services.fetch_service import HtmlScrapeSource, NewsSource, RssSource, fetch_all_sources
from src.storage.repository import Repository

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_RSS_FEEDS_FILE = _DATA_DIR / "rss_feeds.txt"
_USER_PROFILE_FILE = _DATA_DIR / "user_profile.json"


def _feed_name(feed_url: str) -> str:
    host = urlparse(feed_url).netloc
    for prefix in ("www.", "feeds.", "rss."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


def load_default_sources() -> list[NewsSource]:
    """Every feed in data/rss_feeds.txt, plus one direct-scraped HTML
    source -- satisfies "at least 5 sources, at least one HTML-scraped"
    (TOPIC.md)."""
    sources: list[NewsSource] = []
    if _RSS_FEEDS_FILE.exists():
        for line in _RSS_FEEDS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            sources.append(RssSource(feed_url=line, name=_feed_name(line)))
    sources.append(
        HtmlScrapeSource(
            listing_url=settings.html_scrape_url,
            name=settings.html_scrape_source_name,
        )
    )
    return sources


async def load_user(repository: Repository, user_id: str) -> User:
    """Load the user's profile from PostgreSQL, seeding it from the bundled
    `data/user_profile.json` sample on first run for the demo user, and
    otherwise falling back to an unfiltered default."""
    user = await repository.get_user(user_id)
    if user is not None:
        return user

    if _USER_PROFILE_FILE.exists():
        raw = json.loads(_USER_PROFILE_FILE.read_text(encoding="utf-8"))
        if raw.get("user") == user_id:
            user = User(
                user_id=user_id,
                preferred_topics=raw.get("preferred_topics", []),
                excluded_sources=raw.get("excluded_sources", []),
            )
            await repository.save_user(user)
            return user

    logger.warning("No stored profile for %s; using an unfiltered default.", user_id)
    return User(user_id=user_id)


async def _already_processed_urls(repository: Repository, raw_articles: list) -> set[str]:
    """Canonical URLs from `raw_articles` that a *previous* run already
    processed, checked concurrently against the persistent dedup cache."""
    candidates: set[str] = set()
    for article in raw_articles:
        try:
            candidates.add(url_canonicalize(article.url))
        except ValueError:
            continue
    if not candidates:
        return set()
    ordered = list(candidates)
    results = await asyncio.gather(*(repository.is_url_processed(c) for c in ordered))
    return {url for url, processed in zip(ordered, results) if processed}


async def run_daily_pipeline(user_id: str, *, sources: list[NewsSource] | None = None) -> Path:
    """Run the full pipeline for one user; returns the generated digest path."""
    active_sources = sources or load_default_sources()
    repository = Repository()
    await repository.connect()
    try:
        await repository.init_schema()
        user = await load_user(repository, user_id)

        t0 = time.perf_counter()
        raw_articles = await fetch_all_sources(active_sources)
        fetch_seconds = time.perf_counter() - t0
        logger.info(
            "Fetched %d raw articles from %d sources in %.2fs",
            len(raw_articles), len(active_sources), fetch_seconds,
        )

        already_processed = await _already_processed_urls(repository, raw_articles)
        deduper = Deduplicator(already_processed=already_processed)
        deduped = deduper.run(raw_articles)
        if settings.max_articles_per_run is not None and len(deduped) > settings.max_articles_per_run:
            logger.warning(
                "MAX_ARTICLES_PER_RUN=%d: capping %d deduped articles down to %d "
                "before calling the LLM (development/quota-limited setting -- "
                "leave unset for the real submitted run).",
                settings.max_articles_per_run, len(deduped), settings.max_articles_per_run,
            )
            deduped = deduped[: settings.max_articles_per_run]
        logger.info(
            "Dedup: %d seen -> %d kept (%.0f%% duplicate rate)",
            deduper.stats.seen, deduper.stats.kept, deduper.stats.duplicate_rate * 100,
        )

        ai_service = AIService(repository)
        items: list[DigestItem] = []
        for article in deduped:
            try:
                labeled = await ai_service.summarize_and_label(article)
            except Exception:
                logger.exception("Skipping article %r after repeated AI failures.", article.title)
                continue
            items.append(DigestItem(article=article, labeled_summary=labeled))

        markdown = render_markdown(user_id, items, user)
        return write_digest(user_id, markdown)
    finally:
        await repository.close()
