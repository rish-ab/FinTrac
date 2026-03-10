# =============================================================
# src/engine/alert_monitor.py
#
# Checks every active watchlist item against current prices
# and fires alerts when thresholds are crossed.
#
# CALLED BY: src/engine/scheduler.py every 60 seconds
#
# FLOW PER WATCHLIST ITEM:
#   1. Fetch current price via yfinance
#   2. Check price_trigger_high — alert if price >= threshold
#   3. Check price_trigger_low  — alert if price <= threshold
#   4. If threshold crossed:
#      a. Write AlertQueue row to MariaDB (permanent record)
#      b. Publish event to Redis Stream (real-time delivery)
#
# WHY REDIS STREAMS AND NOT JUST MARIADB?
# MariaDB is the record of truth — every alert is stored there.
# Redis Streams are the delivery mechanism — they're a fast,
# ordered log that the consumer reads and acts on immediately.
# Separating storage from delivery means:
#   - If Redis is down, alerts are still recorded in MariaDB
#   - The consumer can replay missed events after a restart
#   - Delivery logic (email/push) is decoupled from detection
#
# DEDUPLICATION:
# We don't want to fire 60 alerts per hour just because XOM
# stays above the trigger price. We check if an undelivered
# alert already exists for this watchlist item + alert_type
# before creating a new one.
# =============================================================

import json
from datetime import datetime

import redis.asyncio as aioredis
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AlertQueue, AssetMaster, Watchlist
from src.db.session import AsyncSessionFactory
from src.ingestion.yf_client import fetch_market_snapshot

# Redis stream name — all price alerts go into this stream
ALERT_STREAM = "fintrac:alerts"


# ── DEDUPLICATION CHECK ────────────────────────────────────────────────────────

async def _alert_already_pending(
    watchlist_id: str,
    alert_type:   str,
    db:           AsyncSession,
) -> bool:
    """
    Returns True if there's already a PENDING or SENT alert
    for this watchlist item and alert type.
    Prevents alert spam when price stays above/below threshold.
    """
    result = await db.execute(
        select(AlertQueue).where(
            AlertQueue.watchlist_id == watchlist_id,
            AlertQueue.alert_type   == alert_type,
            AlertQueue.status.in_(["PENDING", "SENT"]),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


# ── FIRE ONE ALERT ─────────────────────────────────────────────────────────────

async def _fire_alert(
    watchlist_item: Watchlist,
    alert_type:     str,        # PRICE_HIGH or PRICE_LOW
    trigger_value:  float,
    current_price:  float,
    ticker:         str,
    redis_client:   aioredis.Redis,
    db:             AsyncSession,
) -> None:
    """
    Write an AlertQueue row to MariaDB and publish to Redis Stream.
    """
    # ── MARIADB RECORD ─────────────────────────────────────────
    alert = AlertQueue(
        user_id       = watchlist_item.user_id,
        watchlist_id  = watchlist_item.id,
        alert_type    = alert_type,
        trigger_value = trigger_value,
        triggered_at  = datetime.utcnow(),
        delivered_at  = None,
        channel       = "STREAM",
        status        = "PENDING",
    )
    db.add(alert)
    await db.flush()   # get alert.id before publishing to Redis

    # ── REDIS STREAM EVENT ─────────────────────────────────────
    # XADD appends an event to the stream.
    # "*" means Redis auto-generates the message ID (timestamp-based).
    # The consumer reads these in order via XREADGROUP.
    event_payload = {
        "alert_id":     alert.id,
        "user_id":      watchlist_item.user_id,
        "watchlist_id": watchlist_item.id,
        "ticker":       ticker,
        "alert_type":   alert_type,
        "trigger_value": str(trigger_value),
        "current_price": str(current_price),
        "triggered_at": alert.triggered_at.isoformat(),
    }

    await redis_client.xadd(ALERT_STREAM, event_payload)

    await db.commit()

    logger.info(
        f"ALERT FIRED: {ticker} {alert_type} | "
        f"trigger={trigger_value} current={current_price} | "
        f"alert_id={alert.id[:8]}..."
    )


# ── MONITOR ONE WATCHLIST ITEM ─────────────────────────────────────────────────

async def _check_watchlist_item(
    item:         Watchlist,
    ticker:       str,
    redis_client: aioredis.Redis,
    db:           AsyncSession,
) -> int:
    """
    Check a single watchlist item against current price.
    Returns number of alerts fired (0, 1, or 2).
    """
    # No price triggers set — nothing to check
    if item.price_trigger_high is None and item.price_trigger_low is None:
        return 0

    # Fetch current price
    snapshot = await fetch_market_snapshot(ticker)
    if snapshot.current_price is None:
        logger.warning(f"Could not fetch price for {ticker} — skipping alert check")
        return 0

    price    = snapshot.current_price
    fired    = 0

    # ── HIGH THRESHOLD ─────────────────────────────────────────
    if item.price_trigger_high is not None and price >= item.price_trigger_high:
        if not await _alert_already_pending(item.id, "PRICE_HIGH", db):
            await _fire_alert(
                watchlist_item = item,
                alert_type     = "PRICE_HIGH",
                trigger_value  = item.price_trigger_high,
                current_price  = price,
                ticker         = ticker,
                redis_client   = redis_client,
                db             = db,
            )
            fired += 1
        else:
            logger.debug(
                f"{ticker} above {item.price_trigger_high} "
                f"but alert already pending — skipping"
            )

    # ── LOW THRESHOLD ──────────────────────────────────────────
    if item.price_trigger_low is not None and price <= item.price_trigger_low:
        if not await _alert_already_pending(item.id, "PRICE_LOW", db):
            await _fire_alert(
                watchlist_item = item,
                alert_type     = "PRICE_LOW",
                trigger_value  = item.price_trigger_low,
                current_price  = price,
                ticker         = ticker,
                redis_client   = redis_client,
                db             = db,
            )
            fired += 1

    return fired


# ── MAIN MONITOR RUN ───────────────────────────────────────────────────────────

async def run_alert_monitor(redis_client: aioredis.Redis) -> None:
    """
    Check all active watchlist items with price triggers.
    Called by the scheduler every 60 seconds.
    """
    async with AsyncSessionFactory() as db:
        # Fetch all watchlist items that have at least one price trigger
        result = await db.execute(
            select(Watchlist, AssetMaster.ticker_symbol)
            .join(AssetMaster, Watchlist.asset_id == AssetMaster.asset_id)
            .where(
                (Watchlist.price_trigger_high.isnot(None)) |
                (Watchlist.price_trigger_low.isnot(None))
            )
        )
        rows = result.all()

        if not rows:
            logger.debug("Alert monitor: no watchlist items with price triggers")
            return

        logger.info(f"Alert monitor: checking {len(rows)} watchlist items")

        total_fired = 0
        for item, ticker in rows:
            try:
                fired = await _check_watchlist_item(
                    item, ticker, redis_client, db
                )
                total_fired += fired
            except Exception as e:
                logger.error(
                    f"Alert check failed for {ticker} "
                    f"(watchlist_id={item.id[:8]}...): {e}"
                )

        if total_fired:
            logger.info(f"Alert monitor: {total_fired} alerts fired this run")
        else:
            logger.debug("Alert monitor: no thresholds crossed this run")