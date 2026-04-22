"""Nightly metrics dump for Relay central API.

Usage:
    source .venv/bin/activate
    python scripts/metrics.py                # reads RELAY_DATABASE_URL
    python scripts/metrics.py --url "$URL"   # override

Prints: skill count, uploads-24h, reviews-24h, avg confidence, stale count,
top-5 most-used skills, bottom-5 lowest-confidence active skills.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


QUERIES = {
    "total_active": "SELECT COUNT(*) FROM skills WHERE status = 'active'",
    "total_stale": "SELECT COUNT(*) FROM skills WHERE status = 'stale'",
    "uploads_24h": "SELECT COUNT(*) FROM skills WHERE created_at > NOW() - INTERVAL '24 hours'",
    "reviews_24h": "SELECT COUNT(*) FROM reviews WHERE created_at > NOW() - INTERVAL '24 hours'",
    "avg_confidence": (
        "SELECT ROUND(AVG(confidence)::numeric, 3) FROM skills WHERE status = 'active'"
    ),
    "top_used": (
        "SELECT name, used_count, confidence FROM skills "
        "WHERE status = 'active' ORDER BY used_count DESC LIMIT 5"
    ),
    "lowest_conf": (
        "SELECT name, confidence, good_count, bad_count FROM skills "
        "WHERE status = 'active' AND (good_count + bad_count) >= 2 "
        "ORDER BY confidence ASC LIMIT 5"
    ),
}


async def run(url: str) -> int:
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            for name, q in QUERIES.items():
                result = await conn.execute(text(q))
                rows = result.fetchall()
                print(f"\n== {name} ==")
                for row in rows:
                    print("  " + " | ".join(str(x) for x in row))
    finally:
        await engine.dispose()
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=os.environ.get("RELAY_DATABASE_URL"))
    args = p.parse_args()
    if not args.url:
        print("error: --url or RELAY_DATABASE_URL required", file=sys.stderr)
        return 2
    return asyncio.run(run(args.url))


if __name__ == "__main__":
    raise SystemExit(main())
