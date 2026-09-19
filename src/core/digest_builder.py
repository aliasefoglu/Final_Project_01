"""Markdown digest rendering and atomic file output.

`render_markdown`, `filter_for_user`, and `group_by_topic` are pure
functions -- trivially unit-testable without any I/O. Only `write_digest`
touches the filesystem, and it does so atomically (write to a temp file in
the same directory, then `os.replace`) so a crash mid-write never leaves a
corrupt or half-written digest on disk.
"""

from __future__ import annotations

import logging
import os
import tempfile
from contextlib import suppress
from datetime import date, datetime, timezone
from pathlib import Path

from src.config import settings
from src.models import Article, LabeledSummary, SentimentEnum, TopicEnum, User

logger = logging.getLogger(__name__)

_SENTIMENT_GLYPH = {
    SentimentEnum.POSITIVE: "+",
    SentimentEnum.NEUTRAL: "=",
    SentimentEnum.NEGATIVE: "-",
}


class DigestItem:
    """Pairs a raw article with its AI-generated label for rendering."""

    __slots__ = ("article", "labeled_summary")

    def __init__(self, article: Article, labeled_summary: LabeledSummary) -> None:
        self.article = article
        self.labeled_summary = labeled_summary


def filter_for_user(items: list[DigestItem], user: User) -> list[DigestItem]:
    """Keep items matching the user's preferred topics, dropping anything
    from an excluded source. An empty `preferred_topics` means "no filter"
    (send everything, as a sensible default for a brand-new account)."""
    excluded = {s.lower() for s in user.excluded_sources}
    preferred = set(user.preferred_topics)
    kept = []
    for item in items:
        if item.article.source.lower() in excluded:
            continue
        if preferred and item.labeled_summary.topic not in preferred:
            continue
        kept.append(item)
    return kept


def group_by_topic(items: list[DigestItem], user: User) -> dict[TopicEnum, list[DigestItem]]:
    """Group items by topic, ordered by the user's stated topic preference
    first, then any remaining topics in their enum declaration order."""
    grouped: dict[TopicEnum, list[DigestItem]] = {}
    for item in items:
        grouped.setdefault(item.labeled_summary.topic, []).append(item)

    ordered_topics = list(user.preferred_topics) + [
        t for t in TopicEnum if t not in user.preferred_topics
    ]
    return {t: grouped[t] for t in ordered_topics if t in grouped}


def render_markdown(
    user_id: str,
    items: list[DigestItem],
    user: User,
    *,
    generated_at: datetime | None = None,
) -> str:
    """Render a personalized Markdown digest for `user_id`. Pure -- no I/O."""
    generated_at = generated_at or datetime.now(timezone.utc)
    relevant = filter_for_user(items, user)
    grouped = group_by_topic(relevant, user)

    lines = [
        f"# Daily digest for {user_id}",
        f"_Generated {generated_at.isoformat(timespec='seconds')}_",
        "",
    ]
    if not grouped:
        lines.append("_No new articles matched your preferences today._")
        return "\n".join(lines)

    for topic, topic_items in grouped.items():
        lines.append(f"## {topic.value}")
        lines.append("")
        for item in topic_items:
            glyph = _SENTIMENT_GLYPH[item.labeled_summary.sentiment]
            lines.append(f"- **{item.article.title}** ({item.article.source})  [{glyph}]")
            lines.append(f"  {item.labeled_summary.summary}")
            lines.append(f"  <{item.article.url}>")
            lines.append("")
    return "\n".join(lines)


def digest_path(user_id: str, *, on: date | None = None) -> Path:
    on = on or date.today()
    directory = Path(settings.digests_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{on.isoformat()}-{user_id}.md"


def write_digest(user_id: str, markdown: str, *, on: date | None = None) -> Path:
    """Write `markdown` to `digests/YYYY-MM-DD-<user>.md` atomically."""
    target = digest_path(user_id, on=on)
    fd, tmp_path = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(markdown)
        os.replace(tmp_path, target)
    except Exception:
        with suppress(OSError):
            os.remove(tmp_path)
        raise
    logger.info("Digest written to %s", target)
    return target
