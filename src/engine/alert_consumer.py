# =============================================================
# src/engine/alert_consumer.py
#
# Reads alert events from the Redis Stream and marks them
# as delivered in MariaDB.
#
# WHY A CONSUMER GROUP?
# Redis consumer groups let multiple consumers share the work
# of processing a stream. More importantly, they track which
# messages have been acknowledged (ACK'd) — if the consumer
# crashes mid-processing, unACK'd messages can be reclaimed
# and retried. This makes delivery reliable.
#
# CONSUMER GROUP PATTERN:
#   XREADGROUP GROUP fintrac-consumers consumer-1 ...
#     → reads N unprocessed messages assigned to consumer-1
#     → processes each message
#     → XACK GROUP fintrac-consumers <message-id>
#        → marks it as done, won't be re-delivered
#
# CURRENT DELIVERY:
# For now "delivery" means marking the alert as SENT in MariaDB
# and logging it. In production you'd add:
#   - Email via SendGrid/SES
#   - Push notification via Firebase
#   - Slack/Telegram webhook
# The consumer is the right place for all of these — the
# monitor fires the event, the consumer delivers it.
# =============================================================

import asyncio

import redis.asyncio as aioredis
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from src.db.models import AlertQueue
from src.db.session import AsyncSessionFactory

ALERT_STREAM      = "fintrac:alerts"
CONSUMER_GROUP    = "fintrac-consumers"
CONSUMER_NAME     = "consumer-1"
BLOCK_MS          = 5000    # block for 5 seconds waiting for new messages
BATCH_SIZE        = 10      # read up to 10 messages at once


# ── SETUP CONSUMER GROUP ───────────────────────────────────────────────────────

async def ensure_consumer_group(redis_client: aioredis.Redis) -> None:
    """
    Create the consumer group if it doesn't exist.
    MKSTREAM creates the stream too if it doesn't exist yet.
    Safe to call on every startup — BUSYGROUP error is ignored.
    """
    try:
        await redis_client.xgroup_create(
            name     = ALERT_STREAM,
            groupname= CONSUMER_GROUP,
            id       = "0",         # start from the beginning of the stream
            mkstream = True,        # create stream if it doesn't exist
        )
        logger.info(
            f"Redis consumer group '{CONSUMER_GROUP}' created "
            f"on stream '{ALERT_STREAM}'"
        )
    except aioredis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.debug(f"Consumer group '{CONSUMER_GROUP}' already exists")
        else:
            raise


# ── PROCESS ONE MESSAGE ────────────────────────────────────────────────────────

async def _process_message(
    message_id: str,
    fields:     dict,
    db:         AsyncSession,
) -> bool:
    """
    Handle a single alert event from the stream.
    Returns True if processed successfully, False on failure.
    """
    alert_id    = fields.get("alert_id")
    ticker      = fields.get("ticker", "UNKNOWN")
    alert_type  = fields.get("alert_type", "UNKNOWN")
    curr_price  = fields.get("current_price", "N/A")
    trigger_val = fields.get("trigger_value", "N/A")

    if not alert_id:
        logger.warning(f"Message {message_id} missing alert_id — skipping")
        return True   # ACK anyway to avoid reprocessing bad messages

    # ── MARK AS DELIVERED IN MARIADB ──────────────────────────
    result = await db.execute(
        select(AlertQueue).where(AlertQueue.id == alert_id)
    )
    alert = result.scalar_one_or_none()

    if not alert:
        logger.warning(f"Alert {alert_id} not found in DB — may have been deleted")
        return True   # ACK anyway

    alert.status       = "SENT"
    alert.delivered_at = datetime.utcnow()
    await db.commit()

    # ── DELIVERY ACTION ────────────────────────────────────────
    # Currently: structured log entry (visible in docker compose logs)
    # Future: swap this for email/push/webhook
    direction = "above" if alert_type == "PRICE_HIGH" else "below"
    logger.info(
        f"🔔 ALERT DELIVERED | {ticker} is {direction} ${trigger_val} "
        f"(current: ${curr_price}) | alert_id={alert_id[:8]}..."
    )

    return True


# ── CONSUMER LOOP ──────────────────────────────────────────────────────────────

async def run_consumer(redis_client: aioredis.Redis) -> None:
    """
    Continuously reads from the Redis Stream and processes alerts.
    Runs as a long-lived background task started from main.py lifespan.

    Two reads per iteration:
    1. Pending messages (id=0) — messages delivered but not yet ACK'd
       These are retried on every startup to handle crash recovery.
    2. New messages (id=>) — messages not yet delivered to any consumer
    """
    await ensure_consumer_group(redis_client)
    logger.info("Alert consumer started — listening on stream fintrac:alerts")

    while True:
        try:
            async with AsyncSessionFactory() as db:
                # First pass: retry any pending (unACK'd) messages
                pending = await redis_client.xreadgroup(
                    groupname    = CONSUMER_GROUP,
                    consumername = CONSUMER_NAME,
                    streams      = {ALERT_STREAM: "0"},
                    count        = BATCH_SIZE,
                )

                if pending:
                    for stream_name, messages in pending:
                        for message_id, fields in messages:
                            success = await _process_message(
                                message_id, fields, db
                            )
                            if success:
                                await redis_client.xack(
                                    ALERT_STREAM, CONSUMER_GROUP, message_id
                                )

                # Second pass: read new messages (blocks up to BLOCK_MS)
                new_messages = await redis_client.xreadgroup(
                    groupname    = CONSUMER_GROUP,
                    consumername = CONSUMER_NAME,
                    streams      = {ALERT_STREAM: ">"},
                    count        = BATCH_SIZE,
                    block        = BLOCK_MS,
                )

                if new_messages:
                    for stream_name, messages in new_messages:
                        for message_id, fields in messages:
                            success = await _process_message(
                                message_id, fields, db
                            )
                            if success:
                                await redis_client.xack(
                                    ALERT_STREAM, CONSUMER_GROUP, message_id
                                )

        except aioredis.ConnectionError as e:
            logger.error(f"Redis connection lost in consumer: {e} — retrying in 5s")
            await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Unexpected error in alert consumer: {e} — retrying in 5s")
            await asyncio.sleep(5)