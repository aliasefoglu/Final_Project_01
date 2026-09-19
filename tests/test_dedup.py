"""Unit tests for src.core.dedup.Deduplicator."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.core.dedup import Deduplicator
from src.models import Article


def make_article(
    *,
    id: str = "a1",
    title: str = "Acme unveils new processor",
    url: str = "https://example.com/news/acme-chip",
    source: str = "Example News",
    content: str | None = None,
) -> Article:
    return Article(
        id=id,
        title=title,
        content=content
        or (
            "Acme Corp announced a new processor today aimed at AI workloads. "
            "The chip features improved energy efficiency over the previous "
            "generation. Industry analysts welcomed the news."
        ),
        url=url,
        source=source,
        published_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
    )


@pytest.fixture
def deduper() -> Deduplicator:
    return Deduplicator(near_duplicate_threshold=0.7)


def test_normalize_attaches_canonical_url_and_content_hash(deduper: Deduplicator) -> None:
    article = make_article(url="https://Example.com/news/acme-chip?utm_source=twitter")
    normalized = deduper.normalize(article)
    assert normalized is not None
    assert normalized.canonical_url == "https://example.com/news/acme-chip"
    assert normalized.content_hash is not None
    assert len(normalized.content_hash) == 64  # SHA-256 hex digest


def test_normalize_rejects_malformed_url(deduper: Deduplicator) -> None:
    article = make_article(url="not a url")
    assert deduper.normalize(article) is None
    assert deduper.stats.rejected_malformed == 1


def test_normalize_rejects_empty_content(deduper: Deduplicator) -> None:
    article = make_article(content="   ")
    assert deduper.normalize(article) is None
    assert deduper.stats.rejected_malformed == 1


def test_offer_keeps_first_occurrence(deduper: Deduplicator) -> None:
    kept = deduper.offer(make_article(id="a1"))
    assert kept is not None
    assert deduper.stats.kept == 1
    assert deduper.stats.seen == 1


def test_offer_rejects_exact_url_duplicate(deduper: Deduplicator) -> None:
    deduper.offer(make_article(id="a1", url="https://example.com/story?utm_source=fb"))
    result = deduper.offer(make_article(id="a2", url="https://example.com/story?utm_source=ig"))
    assert result is None
    assert deduper.stats.rejected_exact == 1
    assert deduper.stats.kept == 1


def test_offer_rejects_exact_content_duplicate_across_different_urls(deduper: Deduplicator) -> None:
    same_body = "The city council approved the new transit budget on Tuesday."
    deduper.offer(make_article(id="a1", url="https://a.com/story", content=same_body))
    result = deduper.offer(make_article(id="a2", url="https://b.com/story", content=same_body))
    assert result is None
    assert deduper.stats.rejected_exact == 1


def test_offer_rejects_near_duplicate_content(deduper: Deduplicator) -> None:
    original = (
        "The mayor announced a new infrastructure plan today, covering roads, "
        "bridges, and public transit upgrades across the entire city."
    )
    rewritten = (
        "The mayor announced a new infrastructure plan today, covering roads, "
        "bridges, and public transit upgrades across the whole city."
    )
    deduper.offer(make_article(id="a1", url="https://a.com/story", content=original))
    result = deduper.offer(make_article(id="a2", url="https://b.com/story", content=rewritten))
    assert result is None
    assert deduper.stats.rejected_near_duplicate == 1


def test_offer_keeps_unrelated_articles(deduper: Deduplicator) -> None:
    deduper.offer(make_article(id="a1", url="https://a.com/tech-story"))
    result = deduper.offer(
        make_article(
            id="a2",
            url="https://b.com/sports-story",
            content="The local team won the championship match last night in front of a record crowd.",
        )
    )
    assert result is not None
    assert deduper.stats.kept == 2


def test_offer_rejects_previously_processed_canonical_url() -> None:
    deduper = Deduplicator(already_processed={"https://example.com/news/acme-chip"})
    result = deduper.offer(make_article(url="https://example.com/news/acme-chip"))
    assert result is None
    assert deduper.stats.rejected_exact == 1


def test_run_preserves_order_and_filters(deduper: Deduplicator) -> None:
    articles = [
        make_article(id="a1", url="https://a.com/1", content="First unique story about robotics research."),
        make_article(id="a1-dup", url="https://a.com/1?utm_source=x", content="irrelevant, url dup"),
        make_article(id="a2", url="https://a.com/2", content="Second unique story about ocean currents."),
    ]
    kept = deduper.run(articles)
    assert [a.id for a in kept] == ["a1", "a2"]
    assert deduper.stats.seen == 3
    assert deduper.stats.kept == 2


def test_duplicate_rate_reports_zero_when_nothing_seen(deduper: Deduplicator) -> None:
    assert deduper.stats.duplicate_rate == 0.0
