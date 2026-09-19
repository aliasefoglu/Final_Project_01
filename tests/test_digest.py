"""Unit tests for src.core.digest_builder."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.core.digest_builder import (
    DigestItem,
    digest_path,
    filter_for_user,
    group_by_topic,
    render_markdown,
    write_digest,
)
from src.models import Article, LabeledSummary, SentimentEnum, TopicEnum, User


def make_item(
    *,
    title: str = "A tech story",
    source: str = "Example News",
    topic: TopicEnum = TopicEnum.TECH,
    sentiment: SentimentEnum = SentimentEnum.NEUTRAL,
    url: str = "https://example.com/a",
) -> DigestItem:
    article = Article(
        id=title,
        title=title,
        content="Some article body text that is long enough to be meaningful.",
        url=url,
        source=source,
        published_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
    )
    labeled = LabeledSummary(summary="A short summary.", topic=topic, sentiment=sentiment)
    return DigestItem(article=article, labeled_summary=labeled)


def test_filter_for_user_drops_excluded_source() -> None:
    items = [make_item(source="Sponsored Blog"), make_item(source="Trusted News")]
    user = User(user_id="ali", excluded_sources=["Sponsored Blog"])
    result = filter_for_user(items, user)
    assert len(result) == 1
    assert result[0].article.source == "Trusted News"


def test_filter_for_user_keeps_everything_when_no_preferred_topics() -> None:
    items = [make_item(topic=TopicEnum.TECH), make_item(topic=TopicEnum.SPORTS)]
    user = User(user_id="ali")
    assert len(filter_for_user(items, user)) == 2


def test_filter_for_user_restricts_to_preferred_topics() -> None:
    items = [make_item(topic=TopicEnum.TECH), make_item(topic=TopicEnum.SPORTS)]
    user = User(user_id="ali", preferred_topics=[TopicEnum.TECH])
    result = filter_for_user(items, user)
    assert len(result) == 1
    assert result[0].labeled_summary.topic == TopicEnum.TECH


def test_group_by_topic_orders_by_user_preference() -> None:
    items = [make_item(topic=TopicEnum.SCIENCE), make_item(topic=TopicEnum.TECH)]
    user = User(user_id="ali", preferred_topics=[TopicEnum.TECH, TopicEnum.SCIENCE])
    grouped = group_by_topic(items, user)
    assert list(grouped.keys()) == [TopicEnum.TECH, TopicEnum.SCIENCE]


def test_render_markdown_includes_title_summary_and_link() -> None:
    items = [make_item(title="Robots learn to juggle", url="https://example.com/robots")]
    user = User(user_id="khagani", preferred_topics=[TopicEnum.TECH])
    md = render_markdown("khagani", items, user, generated_at=datetime(2026, 5, 6, tzinfo=timezone.utc))
    assert "# Daily digest for khagani" in md
    assert "## Tech" in md
    assert "Robots learn to juggle" in md
    assert "<https://example.com/robots>" in md


def test_render_markdown_reports_no_matches() -> None:
    items = [make_item(topic=TopicEnum.SPORTS)]
    user = User(user_id="khagani", preferred_topics=[TopicEnum.TECH])
    md = render_markdown("khagani", items, user)
    assert "No new articles matched your preferences today" in md


def test_write_digest_creates_file_at_expected_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("src.core.digest_builder.settings.digests_dir", str(tmp_path))
    path = write_digest("khagani", "# hello", on=date(2026, 5, 6))
    assert path == tmp_path / "2026-05-06-khagani.md"
    assert path.read_text(encoding="utf-8") == "# hello"


def test_write_digest_overwrites_atomically(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("src.core.digest_builder.settings.digests_dir", str(tmp_path))
    write_digest("khagani", "first", on=date(2026, 5, 6))
    path = write_digest("khagani", "second", on=date(2026, 5, 6))
    assert path.read_text(encoding="utf-8") == "second"
    # no leftover temp files
    assert list(tmp_path.glob("*.tmp")) == []


def test_digest_path_creates_directory(tmp_path, monkeypatch) -> None:
    target_dir = tmp_path / "nested" / "digests"
    monkeypatch.setattr("src.core.digest_builder.settings.digests_dir", str(target_dir))
    path = digest_path("ali", on=date(2026, 1, 1))
    assert target_dir.exists()
    assert path.name == "2026-01-01-ali.md"
