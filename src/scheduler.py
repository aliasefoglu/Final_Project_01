"""Daily scheduling for the news-briefing pipeline.

Runs `run_daily_pipeline` for every configured user at a fixed local time
every day, then blocks. This is exactly the process the Docker container's
long-running `CMD` invokes (see Dockerfile / docker-compose.yml) -- run it
locally the same way:

    python -m src.scheduler

Configuration (env vars, all optional):
    NEWSBRIEF_USERS            comma-separated user ids (default: "khagani")
    NEWSBRIEF_SCHEDULE_HOUR    local hour to run at, 0-23  (default: 6)
    NEWSBRIEF_SCHEDULE_MINUTE  local minute to run at, 0-59 (default: 0)
"""

from __future__ import annotations

import asyncio
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.cli import configure_logging
from src.concurrency.pipeline import run_daily_pipeline

logger = logging.getLogger(__name__)


def _configured_users() -> list[str]:
    raw = os.getenv("NEWSBRIEF_USERS", "khagani")
    return [u.strip() for u in raw.split(",") if u.strip()]


async def _run_for_all_users() -> None:
    for user_id in _configured_users():
        try:
            path = await run_daily_pipeline(user_id)
            logger.info("Scheduled run complete for %s -> %s", user_id, path)
        except Exception:
            logger.exception("Scheduled run failed for user %s", user_id)


def build_scheduler() -> AsyncIOScheduler:
    hour = int(os.getenv("NEWSBRIEF_SCHEDULE_HOUR", "6"))
    minute = int(os.getenv("NEWSBRIEF_SCHEDULE_MINUTE", "0"))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_for_all_users,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily-briefing",
        replace_existing=True,
    )
    return scheduler


async def _main() -> None:
    configure_logging()
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("Scheduler started; waiting for the next scheduled run.")
    try:
        await asyncio.Event().wait()  # block forever until interrupted
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(_main())
