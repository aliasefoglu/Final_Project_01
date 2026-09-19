"""Sequential-vs-concurrent fetch benchmark.

Reproduces the numbers that belong in README.md's benchmark table and
report.pdf S3.2. Run it from the project root (needs a working .env, since
it makes real HTTP calls to the configured sources):

    python scripts/bench.py --N 20 [--max-parallel 8]

N controls how many fetch operations to run, cycling through the real
source list (data/rss_feeds.txt plus the configured HTML-scrape source) --
so the same handful of real feeds can simulate a larger workload without
needing N distinct sources to exist.

Both the sequential and concurrent runs re-fetch the same N operations for
a fair comparison; expect real-world numbers to vary run-to-run with
network conditions, unlike a synthetic sleep-based benchmark.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.concurrency.pipeline import load_default_sources  # noqa: E402
from src.services.fetch_service import NewsSource, fetch_all_sources  # noqa: E402


def build_workload(n: int) -> list[NewsSource]:
    base_sources = load_default_sources()
    if not base_sources:
        raise SystemExit("No sources configured -- check data/rss_feeds.txt.")
    return [base_sources[i % len(base_sources)] for i in range(n)]


async def timed_fetch(sources: list[NewsSource], *, max_parallel: int) -> float:
    start = time.perf_counter()
    await fetch_all_sources(sources, max_parallel=max_parallel)
    return time.perf_counter() - start


async def main(n: int, max_parallel: int) -> None:
    workload = build_workload(n)
    source_count = len(load_default_sources())

    print(f"Workload: {n} fetch operations (cycling {source_count} configured sources)\n")

    print(f"Running sequential baseline (max_parallel=1, {n} operations, one at a time)...")
    sequential_seconds = await timed_fetch(workload, max_parallel=1)
    print(f"  -> {sequential_seconds:.2f}s\n")

    print(f"Running concurrent (max_parallel={max_parallel})...")
    concurrent_seconds = await timed_fetch(workload, max_parallel=max_parallel)
    print(f"  -> {concurrent_seconds:.2f}s\n")

    speedup = sequential_seconds / concurrent_seconds if concurrent_seconds > 0 else float("inf")

    print("=" * 66)
    print(f"{'Workload':<20}{'N':>4}{'Sequential (s)':>18}{'Concurrent (s)':>18}{'Speedup':>8}")
    print(
        f"{'fetch (N sources)':<20}{n:>4}{sequential_seconds:>18.2f}"
        f"{concurrent_seconds:>18.2f}{speedup:>7.1f}x"
    )
    print("=" * 66)
    print("\nPaste this row into README.md's benchmark table and report.pdf S3.2.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--N", type=int, default=20, dest="n", help="number of fetch operations to simulate (default: 20)")
    parser.add_argument("--max-parallel", type=int, default=8, help="semaphore bound for the concurrent run (default: 8)")
    args = parser.parse_args()
    asyncio.run(main(args.n, args.max_parallel))
