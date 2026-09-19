import asyncpg
from pathlib import Path
from typing import Optional
import json
from src.config import settings
from src.models import (Account, LabeledSummary, SentimentEnum, TopicEnum, User)
class Repository:
    """It provides asynchronous access to the PostgreSQL database"""
    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self) -> None:
        """It creates a PostgreSQL connection pool for asynchronous access to the database."""
        if self.pool is not None:
            return  # Already connected

        # asyncpg expects a standard PostgreSQL DSN.
        database_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        try:
            self.pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=10)
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Failed to connect to the database: {e}") from e

    async def close(self) -> None:
        """It closes the PostgreSQL connection pool."""
        if self.pool is None:
            return  # Already closed
        try:
            await self.pool.close()
        finally:
            self.pool = None

    def _get_pool(self) -> asyncpg.Pool:
        """It returns the PostgreSQL connection pool, raising an error if not connected."""
        if self.pool is None:
            raise RuntimeError("Database connection pool is not initialized. Call connect() first.")
        return self.pool

    _SCHEMA_PATH = Path(__file__).with_name("schema.sql")

    async def init_schema(self) -> None:
        """It creates the database schema if it does not already exist.
        Idempotent: every statement in schema.sql uses IF NOT EXISTS, so calling
        this on every application startup is safe."""
        pool = self._get_pool()
        ddl = self._SCHEMA_PATH.read_text(encoding="utf-8")
        try:
            await pool.execute(ddl)
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Failed to initialize database schema: {e}") from e

    async def get_user(self, user_id: str) -> Optional[User]:
        """It returns a user by ID, or None if the user does not exist.
        Preferred topics and excluded sources live in their own normalized
        tables (user_preferred_topics, user_excluded_sources); this single
        query joins and aggregates them back into lists for the User model."""
        pool = self._get_pool()
        try:
            row = await pool.fetchrow(
                """SELECT u.user_id,
                          u.preferred_length,
                          COALESCE(json_agg(DISTINCT t.topic) FILTER (WHERE t.topic IS NOT NULL), '[]') AS preferred_topics,
                          COALESCE(json_agg(DISTINCT s.source) FILTER (WHERE s.source IS NOT NULL), '[]') AS excluded_sources
                   FROM users u
                   LEFT JOIN user_preferred_topics t ON t.user_id = u.user_id
                   LEFT JOIN user_excluded_sources s ON s.user_id = u.user_id
                   WHERE u.user_id = $1
                   GROUP BY u.user_id, u.preferred_length""",
                user_id,
            )
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Failed to fetch user {user_id} from the database: {e}") from e
        if row is None:
            return None
        preferred_topics = json.loads(row["preferred_topics"])
        excluded_sources = json.loads(row["excluded_sources"])
        return User(
            user_id = row["user_id"],
            preferred_topics = [TopicEnum(topic) for topic in preferred_topics],
            excluded_sources = excluded_sources,
            preferred_length = row["preferred_length"]
        )

    async def save_user(self, user: User) -> None:
        """It adds a new user or updates an existing user, replacing their
        full preferred_topics and excluded_sources sets.
        All three tables (users, user_preferred_topics, user_excluded_sources)
        are written inside a single transaction: without it, a crash between
        deleting a user's old topics and inserting their new ones could leave
        the join tables inconsistent with each other (ACID: atomicity across
        a multi-table write)."""
        pool = self._get_pool()
        preferred_topics = [topic.value for topic in user.preferred_topics]
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """INSERT INTO users (user_id, preferred_length)
                           VALUES ($1, $2)
                           ON CONFLICT (user_id) DO UPDATE
                           SET preferred_length = EXCLUDED.preferred_length""",
                        user.user_id,
                        user.preferred_length,
                    )
                    await conn.execute(
                        """DELETE FROM user_preferred_topics WHERE user_id = $1""",
                        user.user_id,
                    )
                    if preferred_topics:
                        await conn.executemany(
                            """INSERT INTO user_preferred_topics (user_id, topic) VALUES ($1, $2)""",
                            [(user.user_id, topic) for topic in preferred_topics],
                        )
                    await conn.execute(
                        """DELETE FROM user_excluded_sources WHERE user_id = $1""",
                        user.user_id,
                    )
                    if user.excluded_sources:
                        await conn.executemany(
                            """INSERT INTO user_excluded_sources (user_id, source) VALUES ($1, $2)""",
                            [(user.user_id, source) for source in user.excluded_sources],
                        )
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Failed to save user {user.user_id} to the database: {e}") from e

    async def delete_user(self, user_id: str) -> None:
        """It deletes a user by ID from the database."""
        pool = self._get_pool()
        try:
            await pool.execute("""DELETE FROM users WHERE user_id = $1""", user_id)
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Failed to delete user {user_id} from the database: {e}") from e

    async def get_cached_summary(self, content_hash: str) -> Optional[LabeledSummary]:
        """It returns a cached summary by content hash, or None if not found."""
        pool = self._get_pool()
        try:
            row = await pool.fetchrow("""SELECT summary, topic, sentiment FROM processed_urls WHERE content_hash = $1""", content_hash)
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Failed to fetch cached summary for content hash {content_hash} from the database: {e}") from e
        if row is None or row["summary"] is None:
            return None
        return LabeledSummary(
            summary=row["summary"],
            topic=TopicEnum(row["topic"]),
            sentiment=SentimentEnum(row["sentiment"])
        )

    async def save_processed_article(self, canonical_url: str, content_hash: str, labeled_summary: LabeledSummary) -> None:
        """It caches an AI-labeled article result. 
        The content hash is used as the conflict target. 
        If the article already exists, its summary, topic, and sentiment are updated."""
        pool = self._get_pool()
        try:
            await pool.execute(
                """INSERT INTO processed_urls (canonical_url, content_hash, summary, topic, sentiment)
                   VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (content_hash) DO UPDATE
                   SET summary = EXCLUDED.summary,
                       topic = EXCLUDED.topic,
                       sentiment = EXCLUDED.sentiment""",
                canonical_url,
                content_hash,
                labeled_summary.summary,
                labeled_summary.topic.value,
                labeled_summary.sentiment.value
            )
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Failed to save processed article for content hash {content_hash} to the database: {e}") from e

    async def is_url_processed(self, canonical_url: str) -> bool:
        """It checks if a canonical URL is already present in the processed_urls table."""
        pool = self._get_pool()
        try:
            result = await pool.fetchval("""SELECT EXISTS(SELECT 1 FROM processed_urls WHERE canonical_url = $1)""", canonical_url)
            return result is True
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Failed to check if URL {canonical_url} is processed in the database: {e}") from e

    # --- Account operations (web UI authentication) ---------------------

    async def create_account(self, user_id: str, password_hash: str) -> None:
        """It registers a new login credential for an existing user row.
        The caller must have already called save_user() for this user_id,
        since accounts.user_id is a foreign key into users.user_id."""
        pool = self._get_pool()
        try:
            await pool.execute(
                """INSERT INTO accounts (user_id, password_hash, created_at)
                   VALUES ($1, $2, now())""",
                user_id,
                password_hash,
            )
        except asyncpg.UniqueViolationError as e:
            raise ValueError(f"Username {user_id!r} is already taken.") from e
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Failed to create account for {user_id}: {e}") from e

    async def get_account(self, user_id: str) -> Optional[Account]:
        """It returns the login credential for user_id, or None if not registered."""
        pool = self._get_pool()
        try:
            row = await pool.fetchrow(
                """SELECT user_id, password_hash, created_at FROM accounts WHERE user_id = $1""",
                user_id,
            )
        except asyncpg.PostgresError as e:
            raise RuntimeError(f"Failed to fetch account for {user_id}: {e}") from e
        if row is None:
            return None
        return Account(
            user_id=row["user_id"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
        )
