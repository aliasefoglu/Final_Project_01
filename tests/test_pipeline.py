"""End-to-end orchestration tests for src.concurrency.pipeline.

Everything external (network, the AI module, PostgreSQL) is mocked, per
the brief's "all tests run offline" requirement. This is the pipeline's
one required happy-path end-to-end test plus an error-path test.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.concurrency import pipeline
from src.models import Article, LabeledSummary, SentimentEnum, TopicEnum, User


def make_article(article_id: str, url: str, content: str) -> Article:
    return Article(
        id=article_id,
        title=f"Title for {article_id}",
        content=content,
        url=url,
        source="Test Source",
        published_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
    )


@pytest.fixture
def fake_repository(monkeypatch) -> AsyncMock:
    repo = AsyncMock()
    repo.get_user.return_value = User(user_id="khagani", preferred_topics=[TopicEnum.TECH])
    repo.is_url_processed.return_value = False
    repo.get_cached_summary.return_value = None
    monkeypatch.setattr(pipeline, "Repository", lambda: repo)
    return repo


@pytest.mark.asyncio
async def test_run_daily_pipeline_happy_path(fake_repository, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pipeline.settings, "digests_dir", str(tmp_path))

    articles = [
        make_article("a1", "https://a.com/story-one", "A unique story about robotics breakthroughs today."),
        # exact URL duplicate (different tracking param) -> filtered by dedup
        make_article("a2", "https://a.com/story-one?utm_source=x", "irrelevant duplicate body text"),
    ]
    monkeypatch.setattr(pipeline, "fetch_all_sources", AsyncMock(return_value=articles))

    labeled = LabeledSummary(summary="A robotics breakthrough was announced.", topic=TopicEnum.TECH, sentiment=SentimentEnum.POSITIVE)

    class _FakeAIService:
        def __init__(self, repository) -> None:
            self.repository = repository

        async def summarize_and_label(self, article) -> LabeledSummary:
            return labeled

    monkeypatch.setattr(pipeline, "AIService", _FakeAIService)

    path = await pipeline.run_daily_pipeline("khagani", sources=[])

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Daily digest for khagani" in content
    assert "Title for a1" in content
    assert "Title for a2" not in content  # deduped away
    fake_repository.connect.assert_awaited_once()
    fake_repository.close.assert_awaited_once()
    fake_repository.init_schema.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_daily_pipeline_skips_articles_that_fail_ai_labeling(
    fake_repository, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(pipeline.settings, "digests_dir", str(tmp_path))
    articles = [make_article("a1", "https://a.com/story", "Some article content that is long enough.")]
    monkeypatch.setattr(pipeline, "fetch_all_sources", AsyncMock(return_value=articles))

    class _FailingAIService:
        def __init__(self, repository) -> None:
            pass

        async def summarize_and_label(self, article):
            raise RuntimeError("provider is down")

    monkeypatch.setattr(pipeline, "AIService", _FailingAIService)

    path = await pipeline.run_daily_pipeline("khagani", sources=[])

    content = path.read_text(encoding="utf-8")
    assert "No new articles matched your preferences today" in content


@pytest.mark.asyncio
async def test_run_daily_pipeline_closes_repository_even_on_failure(fake_repository, monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "fetch_all_sources", AsyncMock(side_effect=RuntimeError("network down")))

    with pytest.raises(RuntimeError, match="network down"):
        await pipeline.run_daily_pipeline("khagani", sources=[])

    fake_repository.close.assert_awaited_once()


def test_load_default_sources_includes_at_least_five_rss_plus_one_scrape() -> None:
    sources = pipeline.load_default_sources()
    scrape_sources = [s for s in sources if type(s).__name__ == "HtmlScrapeSource"]
    rss_sources = [s for s in sources if type(s).__name__ == "RssSource"]
    assert len(scrape_sources) == 1
    assert len(rss_sources) >= 5
