# =============================================================
# src/ingestion/event_ingester.py
#
# Fetches market news and events from RSS feeds.
# Populates the market_event table for attribution analysis.
#
# WHY RSS FEEDS?
# - Free, no API keys required
# - Real-time financial news
# - Easy to parse
#
# SOURCES:
# - Yahoo Finance RSS
# - Google Finance RSS (fallback)
# =============================================================

import asyncio
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List, Optional

import feedparser
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.v3_models import MarketEvent
from src.db.session import AsyncSessionFactory

# Thread pool for blocking RSS fetches
_thread_pool = ThreadPoolExecutor(max_workers=2)

# RSS Feed URLs
RSS_FEEDS = {
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
    "investing_com": "https://www.investing.com/rss/news.rss",
}


# ── EXTRACT TICKER MENTIONS ────────────────────────────────────────────────────

def _extract_tickers(text: str) -> List[str]:
    """
    Extract ticker symbols from news text.
    Looks for patterns like: TSLA, AAPL, $MSFT, etc.
    """
    if not text:
        return []
    
    # Pattern: 2-5 uppercase letters, optionally preceded by $
    pattern = r'\$?([A-Z]{2,5})(?![a-z])'
    matches = re.findall(pattern, text)
    
    # Filter out common false positives
    stopwords = {'CEO', 'CFO', 'IPO', 'ETF', 'SEC', 'USA', 'USD', 'EU', 'UK', 'US', 'AI', 'IT'}
    tickers = [t for t in matches if t not in stopwords]
    
    # Deduplicate and limit to 5 tickers per article
    return list(dict.fromkeys(tickers))[:5]


# ── EXTRACT SECTORS ────────────────────────────────────────────────────────────

def _extract_sectors(text: str) -> List[str]:
    """
    Extract sector mentions from news text.
    """
    if not text:
        return []
    
    sectors = [
        'Technology', 'Energy', 'Healthcare', 'Financial', 'Consumer',
        'Industrial', 'Materials', 'Utilities', 'Real Estate',
        'Communication', 'Semiconductor', 'Banking', 'Automotive'
    ]
    
    found = []
    text_lower = text.lower()
    for sector in sectors:
        if sector.lower() in text_lower:
            found.append(sector)
    
    return found[:3]  # Limit to 3 sectors


# ── CLASSIFY EVENT TYPE ────────────────────────────────────────────────────────

def _classify_event_type(title: str, description: str) -> str:
    """
    Classify the type of market event based on keywords.
    """
    text = f"{title} {description}".lower()
    
    if any(word in text for word in ['earnings', 'revenue', 'profit', 'quarterly', 'results']):
        return 'EARNINGS'
    elif any(word in text for word in ['fed', 'interest rate', 'federal reserve', 'inflation']):
        return 'FED_ANNOUNCEMENT'
    elif any(word in text for word in ['merger', 'acquisition', 'acquire', 'buyout']):
        return 'MERGER_ACQUISITION'
    elif any(word in text for word in ['ceo', 'cfo', 'executive', 'resignation', 'appointed']):
        return 'LEADERSHIP_CHANGE'
    elif any(word in text for word in ['lawsuit', 'settlement', 'legal', 'regulation']):
        return 'LEGAL_REGULATORY'
    elif any(word in text for word in ['product', 'launch', 'release', 'unveil']):
        return 'PRODUCT_LAUNCH'
    else:
        return 'GENERAL_NEWS'


# ── SENTIMENT SCORING ──────────────────────────────────────────────────────────

def _calculate_sentiment(title: str, description: str) -> float:
    """
    Simple keyword-based sentiment scoring.
    Returns: -1.0 (very negative) to +1.0 (very positive)
    """
    text = f"{title} {description}".lower()
    
    positive_words = [
        'surge', 'soar', 'gain', 'profit', 'beat', 'exceed', 'growth', 'strong',
        'record', 'boost', 'up', 'rise', 'rally', 'bullish', 'outperform'
    ]
    
    negative_words = [
        'plunge', 'drop', 'fall', 'loss', 'miss', 'decline', 'weak', 'slump',
        'crash', 'down', 'bearish', 'underperform', 'concern', 'warning', 'risk'
    ]
    
    pos_count = sum(1 for word in positive_words if word in text)
    neg_count = sum(1 for word in negative_words if word in text)
    
    total = pos_count + neg_count
    if total == 0:
        return 0.0
    
    score = (pos_count - neg_count) / total
    return round(max(-1.0, min(1.0, score)), 2)


# ── FETCH RSS FEED ─────────────────────────────────────────────────────────────

def _fetch_rss_sync(feed_url: str) -> List[dict]:
    """
    Synchronous RSS fetch (runs in thread pool).
    Returns list of parsed entries.
    """
    try:
        feed = feedparser.parse(feed_url)
        
        if not feed.entries:
            logger.warning(f"No entries found in RSS feed: {feed_url}")
            return []
        
        logger.info(f"Fetched {len(feed.entries)} entries from {feed_url}")
        return feed.entries
    
    except Exception as e:
        logger.error(f"Failed to fetch RSS feed {feed_url}: {e}")
        return []


async def fetch_rss_feed(feed_url: str) -> List[dict]:
    """Async wrapper for RSS fetch."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_thread_pool, _fetch_rss_sync, feed_url)


# ── INGEST ONE ARTICLE ─────────────────────────────────────────────────────────

async def _ingest_event(
    entry: dict,
    source: str,
    db: AsyncSession,
) -> Optional[MarketEvent]:
    """
    Create a MarketEvent record from an RSS entry.
    Returns None if duplicate or invalid.
    """
    title = entry.get('title', '').strip()
    description = entry.get('description', '').strip()
    link = entry.get('link', '')
    
    if not title:
        return None
    
    # Parse publish date
    published = entry.get('published_parsed')
    if published:
        event_timestamp = datetime(*published[:6])
    else:
        event_timestamp = datetime.utcnow()
    
    # Generate content hash for deduplication
    content = f"{title}{description}"
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    
    # Check if already ingested
    result = await db.execute(
        select(MarketEvent).where(
            MarketEvent.source == f"{source}|{content_hash[:16]}"
        ).limit(1)
    )
    if result.scalar_one_or_none():
        return None  # Duplicate
    
    # Extract metadata
    tickers = _extract_tickers(f"{title} {description}")
    sectors = _extract_sectors(f"{title} {description}")
    event_type = _classify_event_type(title, description)
    sentiment = _calculate_sentiment(title, description)
    
    # Create event
    event = MarketEvent(
        event_timestamp=event_timestamp,
        event_type=event_type,
        title=title[:500],  # Truncate to schema limit
        description=description[:5000] if description else None,
        source=f"{source}|{content_hash[:16]}",  # Source + hash for dedup
        affected_tickers=tickers if tickers else None,
        affected_sectors=sectors if sectors else None,
        sentiment_score=sentiment,
        embedding_vector=None,  # TODO: Add embedding in Phase 4
    )
    
    db.add(event)
    await db.commit()
    await db.refresh(event)
    
    logger.info(
        f"Ingested event: {title[:50]}... | "
        f"type={event_type} | tickers={tickers} | sentiment={sentiment}"
    )
    
    return event


# ── PUBLIC: INGEST LATEST NEWS ────────────────────────────────────────────────

async def ingest_latest_news(max_articles: int = 20) -> int:
    """
    Fetch latest news from RSS feeds and populate market_event table.
    Returns number of new events ingested.
    """
    logger.info("Starting news ingestion from RSS feeds")
    
    async with AsyncSessionFactory() as db:
        total_ingested = 0
        
        for source_name, feed_url in RSS_FEEDS.items():
            try:
                entries = await fetch_rss_feed(feed_url)
                
                # Process entries (limit to max_articles per source)
                for entry in entries[:max_articles]:
                    try:
                        event = await _ingest_event(entry, source_name, db)
                        if event:
                            total_ingested += 1
                    except Exception as e:
                        logger.error(f"Failed to ingest entry from {source_name}: {e}")
                        continue
            
            except Exception as e:
                logger.error(f"Failed to process feed {source_name}: {e}")
                continue
        
        logger.info(f"News ingestion complete: {total_ingested} new events")
        return total_ingested


# ── SEARCH EVENTS BY TICKER ────────────────────────────────────────────────────

async def get_events_for_ticker(
    ticker: str,
    limit: int = 10,
) -> List[MarketEvent]:
    """
    Get recent events that mention a specific ticker.
    """
    async with AsyncSessionFactory() as db:
        # JSON query: find events where ticker is in affected_tickers array
        result = await db.execute(
            select(MarketEvent)
            .where(MarketEvent.affected_tickers.contains(ticker))
            .order_by(MarketEvent.event_timestamp.desc())
            .limit(limit)
        )
        
        events = list(result.scalars().all())
        logger.info(f"Found {len(events)} events for {ticker}")
        return events
