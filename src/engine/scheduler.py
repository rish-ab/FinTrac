# =============================================================
# src/engine/scheduler.py
#
# Runs background tasks on a fixed interval.
#
# INTERVALS:
#   alert_monitor        → every 60 seconds
#   prediction_evaluator → every 24 hours
#   attribution_analysis → every 24 hours (after evaluator)
#   calibration_engine   → every 7 days  (Phase 5)
#   prompt_evolver       → every 7 days  (Phase 6, after calibration)
# =============================================================

import asyncio
from datetime import datetime, timedelta

import redis.asyncio as aioredis
from loguru import logger

from src.engine.alert_monitor import run_alert_monitor
from src.engine.prediction_evaluator import run_prediction_evaluator
from src.engine.attribution_engine import run_attribution_analysis
from src.engine.calibration_engine import run_calibration_engine
from src.engine.prompt_evolver import run_prompt_evolver

ALERT_CHECK_INTERVAL = 60          # seconds
PREDICTION_EVAL_INTERVAL = 86400   # 24 hours in seconds
CALIBRATION_INTERVAL = 604800      # 7 days in seconds


async def run_scheduler(redis_client: aioredis.Redis) -> None:
    """
    Background scheduler — runs multiple tasks on different intervals.
    Started from main.py lifespan as an asyncio task.
    Runs for the lifetime of the application.
    """
    logger.info(
        f"Scheduler started — "
        f"alert monitor every {ALERT_CHECK_INTERVAL}s, "
        f"prediction evaluator every {PREDICTION_EVAL_INTERVAL}s, "
        f"calibration + prompt evolution every {CALIBRATION_INTERVAL}s"
    )
    
    # Track when each task last ran
    last_alert_check = datetime.utcnow()
    last_prediction_eval = datetime.utcnow()
    last_calibration = datetime.utcnow()
    
    # ── STARTUP SEQUENCE ───────────────────────────────────────
    # Run the full pipeline once at startup so the system is
    # immediately calibrated and has active improvement patches.
    # Order matters: evaluate → attribute → calibrate → evolve
    
    try:
        logger.info("Running initial prediction evaluation on startup...")
        await run_prediction_evaluator()
    except Exception as e:
        logger.error(f"Initial prediction evaluation failed: {e}")
    
    try:
        logger.info("Running initial attribution analysis on startup...")
        await run_attribution_analysis()
    except Exception as e:
        logger.error(f"Initial attribution analysis failed: {e}")
    
    try:
        logger.info("Running initial calibration on startup...")
        result = await run_calibration_engine()
        logger.info(f"Initial calibration result: {result.get('status', 'unknown')}")
    except Exception as e:
        logger.error(f"Initial calibration failed: {e}")
    
    try:
        logger.info("Running initial prompt evolution on startup...")
        result = await run_prompt_evolver()
        logger.info(
            f"Initial prompt evolution: {result.get('patches_created', 0)} new, "
            f"{result.get('total_active_patches', 0)} active"
        )
    except Exception as e:
        logger.error(f"Initial prompt evolution failed: {e}")
    
    # ── MAIN LOOP ──────────────────────────────────────────────
    
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
                
                # Run attribution analysis after evaluator finishes
                try:
                    await run_attribution_analysis()
                except Exception as e:
                    logger.error(f"Scheduler: attribution analysis failed: {e}")
                    
            except Exception as e:
                logger.error(f"Scheduler: prediction evaluator run failed: {e}")
        
        # ── CALIBRATION + EVOLUTION (every 7 days) ─────────────
        # Phase 5 calibration runs first to detect biases.
        # Phase 6 prompt evolver runs after to generate patches
        # based on the latest calibration data.
        if (now - last_calibration).total_seconds() >= CALIBRATION_INTERVAL:
            try:
                # Phase 5: Calibration
                cal_result = await run_calibration_engine()
                logger.info(
                    f"Scheduler: calibration complete — "
                    f"{cal_result.get('profiles_created', 0)} profiles"
                )
                
                # Phase 6: Prompt Evolution (runs after calibration)
                try:
                    evo_result = await run_prompt_evolver()
                    logger.info(
                        f"Scheduler: prompt evolution complete — "
                        f"{evo_result.get('patches_created', 0)} new patches, "
                        f"{evo_result.get('total_active_patches', 0)} active"
                    )
                except Exception as e:
                    logger.error(f"Scheduler: prompt evolution failed: {e}")
                
                last_calibration = now
                
            except Exception as e:
                logger.error(f"Scheduler: calibration engine failed: {e}")
        
        # Sleep for a short interval to avoid busy-waiting
        await asyncio.sleep(10)
