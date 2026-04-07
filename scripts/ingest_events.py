#!/usr/bin/env python3
# =============================================================
# scripts/ingest_events.py
#
# Manual event ingestion trigger for testing
# Usage: python scripts/ingest_events.py
# =============================================================

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.event_ingester import ingest_latest_news


async def main():
    print("🔄 Fetching latest market news...")
    count = await ingest_latest_news(max_articles=10)
    print(f"✅ Ingested {count} new events")


if __name__ == "__main__":
    asyncio.run(main())
