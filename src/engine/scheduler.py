# =============================================================
# src/engine/scheduler.py
#
# Runs background tasks on a fixed interval.
#
# WHY NOT CELERY OR APScheduler?
# For this project, a simple asyncio loop is sufficient and
# keeps the dependency count low. Celery adds a broker, a
# worker process, and significant operational complexity —
# overkill when Redis is already in the stack and all tasks
# are I/O-bound async functions.
#
# HOW IT WORKS:
# run_scheduler() is started as an asyncio background task
# from main.py lifespan. It loops forever, sleeping between
# runs. If a task fails, the error is logged and the scheduler
# continues — one bad run doesn't kill the whole loop.
#
# INTERVALS:
#   alert_monitor → every 60 seconds
#     (yfinance rate limit is generous, 60s is safe)
# =============================================================

import asyncio

import redis.asyncio as aioredis
from loguru import logger

from src.engine.alert_monitor import run_alert_monitor

ALERT_CHECK_INTERVAL = 60   # seconds


async def run_scheduler(redis_client: aioredis.Redis) -> None:
    """
    Background scheduler — runs alert monitor every 60 seconds.
    Started from main.py lifespan as an asyncio task.
    Runs for the lifetime of the application.
    """
    logger.info(
        f"Scheduler started — alert monitor will run "
        f"every {ALERT_CHECK_INTERVAL}s"
    )

    while True:
        try:
            await run_alert_monitor(redis_client)
        except Exception as e:
            # Log but never crash — the scheduler must keep running
            logger.error(f"Scheduler: alert monitor run failed: {e}")

        await asyncio.sleep(ALERT_CHECK_INTERVAL)