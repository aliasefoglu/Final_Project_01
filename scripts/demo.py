"""Scripted, single-command demo of the full pipeline.

Runs the real pipeline (fetch -> dedup -> summarize -> digest) for one
user and prints the resulting Markdown straight to the terminal
Usage:
    python scripts/demo.py --user khagani

Needs a working .env (a real LLM_PROVIDER + API key, and a reachable
PostgreSQL via DATABASE_URL) since it makes real network and LLM calls,
same as `python -m src.cli run-daily --user <name>`.
"""

from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cli import configure_logging  # noqa: E402
from src.concurrency.pipeline import run_daily_pipeline  # noqa: E402


async def main(user: str) -> None:
    configure_logging()
    print(f"Running the full pipeline for user={user!r}...\n")
    path = await run_daily_pipeline(user)
    print(f"\nDigest written to {path}\n")
    print("=" * 72)
    print(path.read_text(encoding="utf-8"))
    print("=" * 72)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user", default="khagani", help="user id to run the digest for (default: khagani)")
    args = parser.parse_args()
    asyncio.run(main(args.user))
