"""Two-stage deduplication wiring around the provided `ai.dedup` primitives.

Stage 1 (cheap): reject an article whose canonical URL or content hash has
already been seen -- either earlier in the same run, or in a previous run
(via the persistent `processed_urls` table, passed in as `already_processed`).

Stage 2 (semantic): among the stage-1 survivors, reject any article whose
body is a near-duplicate (word k-shingle Jaccard >= threshold) of an
article already kept in this run.

The threshold is configurable (`settings.dedup_near_duplicate_threshold`,
default 0.70) so it can be tuned empirically against real feeds without
a code change -- see report.pdf S6 for the tuning discussion and the
50-80% duplicate-rate expectation TOPIC.md calls out for syndicated feeds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ai.dedup import content_hash, near_duplicate, url_canonicalize
from src.config import settings
from src.models import Article

logger = logging.getLogger(__name__)


@dataclass
class DedupStats:
    """Run counters used for the report's duplicate-rate discussion."""

    seen: int = 0
    rejected_malformed: int = 0
    rejected_exact: int = 0
    rejected_near_duplicate: int = 0
    kept: int = 0

    @property
    def duplicate_rate(self) -> float:
        if self.seen == 0:
            return 0.0

        return (
            self.rejected_exact + self.rejected_near_duplicate
        ) / self.seen


class Deduplicator:
    """Stateful two-stage dedup pipeline, scoped to a single pipeline run.

    It tracks canonical URLs / content hashes seen so far in-memory,
    and additionally rejects anything already recorded in a previous
    run via `already_processed`.
    """

    def __init__(
        self,
        *,
        near_duplicate_threshold: float | None = None,
        already_processed: set[str] | None = None,
    ) -> None:
        self.threshold = (
            near_duplicate_threshold
            if near_duplicate_threshold is not None
            else settings.dedup_near_duplicate_threshold
        )

        self._seen_urls: set[str] = set()
        self._seen_hashes: set[str] = set()
        self._kept: list[Article] = []
        self._already_processed: set[str] = already_processed or set()
        self.stats = DedupStats()

    def normalize(self, article: Article) -> Article | None:
        """Attach canonical_url / content_hash to `article`.

        Returns None and increments `rejected_malformed` if the article
        cannot be normalized.
        """
        try:
            canonical = url_canonicalize(article.url)
        except ValueError:
            logger.warning(
                "Rejecting article with malformed URL: %r",
                article.url,
            )
            self.stats.rejected_malformed += 1
            return None

        if not article.content.strip():
            logger.warning(
                "Rejecting article with empty content: %r",
                article.url,
            )
            self.stats.rejected_malformed += 1
            return None

        digest = content_hash(article.content)

        return article.model_copy(
            update={
                "canonical_url": canonical,
                "content_hash": digest,
            }
        )

    def offer(self, article: Article) -> Article | None:
        """Run one article through both deduplication stages.

        Returns the normalized article if it should be kept.
        Otherwise, returns None.
        """
        self.stats.seen += 1

        normalized = self.normalize(article)

        if normalized is None:
            return None

        # --- Stage 1: cheap exact deduplication ---
        #
        # canonical_url and content_hash are optional fields in Article,
        # so check that they are not None before using them in set lookups.
        is_duplicate_url = (
            normalized.canonical_url is not None
            and (
                normalized.canonical_url in self._seen_urls
                or normalized.canonical_url in self._already_processed
            )
        )

        is_duplicate_hash = (
            normalized.content_hash is not None
            and normalized.content_hash in self._seen_hashes
        )

        if is_duplicate_url or is_duplicate_hash:
            self.stats.rejected_exact += 1
            return None

        # --- Stage 2: semantic near-duplicate ---
        #
        # Compare only against articles that survived Stage 1.
        for kept in self._kept:
            if near_duplicate(
                normalized.content,
                kept.content,
                threshold=self.threshold,
            ):
                self.stats.rejected_near_duplicate += 1
                return None

        # Store only non-None values in sets typed as set[str].
        if normalized.canonical_url is not None:
            self._seen_urls.add(normalized.canonical_url)

        if normalized.content_hash is not None:
            self._seen_hashes.add(normalized.content_hash)

        self._kept.append(normalized)
        self.stats.kept += 1

        return normalized

    def run(self, articles: list[Article]) -> list[Article]:
        """Run `offer` over a whole batch, preserving input order."""
        kept: list[Article] = []

        for article in articles:
            result = self.offer(article)

            if result is not None:
                kept.append(result)

        return kept