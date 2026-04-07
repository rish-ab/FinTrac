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
#   prediction_evaluator → every 24 hours
#     (predictions evaluated once daily)
# =============================================================

import asyncio
from datetime import datetime, timedelta

import redis.asyncio as aioredis
from loguru import logger

from src.engine.alert_monitor import run_alert_monitor
from src.engine.prediction_evaluator import run_prediction_evaluator

ALERT_CHECK_INTERVAL = 60   # seconds
PREDICTION_EVAL_INTERVAL = 86400  # 24 hours in seconds


async def run_scheduler(redis_client: aioredis.Redis) -> None:
    """
    Background scheduler — runs multiple tasks on different intervals.
    Started from main.py lifespan as an asyncio task.
    Runs for the lifetime of the application.
    """
    logger.info(
        f"Scheduler started — "
        f"alert monitor every {ALERT_CHECK_INTERVAL}s, "
        f"prediction evaluator every {PREDICTION_EVAL_INTERVAL}s"
    )
    
    # Track when each task last ran
    last_alert_check = datetime.utcnow()
    last_prediction_eval = datetime.utcnow()
    
    # Run prediction evaluator immediately on startup (then every 24h)
    try:
        logger.info("Running initial prediction evaluation on startup...")
        await run_prediction_evaluator()
    except Exception as e:
        logger.error(f"Initial prediction evaluation failed: {e}")
    
    while True:
        now = datetime.utcnow()
        
        # ── ALERT MONITOR (every 60s) ──────────────────────────
        if (now - last_alert_check).total_seconds() >= ALERT_CHECK_INTERVAL:
            try:
                await run_alert_monitor(redis_client)
                last_alert_check = now
            except Exception as e:
                logger.error(f"Scheduler: alert monitor run failed: {e}")
        
        # ── PREDICTION EVALUATOR (every 24h) ───────────────────
        if (now - last_prediction_eval).total_seconds() >= PREDICTION_EVAL_INTERVAL:
            try:
                await run_prediction_evaluator()
                last_prediction_eval = now
            except Exception as e:
                logger.error(f"Scheduler: prediction evaluator run failed: {e}")
        
        # Sleep for a short interval to avoid busy-waiting
        await asyncio.sleep(10)  # Check every 10 seconds