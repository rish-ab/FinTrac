# =============================================================
# src/engine/prediction_evaluator.py
#
# Evaluates past predictions by comparing predicted vs actual
# market performance.
#
# CALLED BY: src/engine/scheduler.py every 24 hours
#
# FLOW:
#   1. Find predictions where evaluation_due_at <= now AND status = 'PENDING'
#   2. For each prediction:
#      a. Fetch current market data
#      b. Calculate actual return vs predicted
#      c. Create PredictionOutcome record
#      d. Update prediction status to 'EVALUATED'
#
# WHY SEPARATE FROM PREDICTION CREATION?
# Separating recording from evaluation allows:
#   - Predictions to be saved immediately (fast API response)
#   - Evaluation to run in batches (efficient)
#   - Retries if market data unavailable
#   - Historical re-evaluation if methodology changes
#
# HORIZON PARSING:
# prediction_horizon is stored as string (e.g., '1w', '1m', '3m')
# We parse this to calculate when evaluation is due.
# =============================================================

from datetime import datetime, timedelta
from typing import Optional

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.v3_models import PredictionRecord, PredictionOutcome
from src.db.session import AsyncSessionFactory
from src.ingestion.yf_client import fetch_market_snapshot


# ── HORIZON PARSING ────────────────────────────────────────────────────────────

def _parse_horizon(horizon_str: str) -> Optional[timedelta]:
    """
    Parse horizon string like '1w', '1m', '3m', '1y' into timedelta.
    Returns None if format is unrecognized.
    
    Examples:
        '1w'  → 7 days
        '2w'  → 14 days
        '1m'  → 30 days (approximate)
        '3m'  → 90 days
        '6m'  → 180 days
        '1y'  → 365 days
    """
    if not horizon_str:
        return None
    
    try:
        # Strip whitespace and convert to lowercase
        horizon = horizon_str.strip().lower()
        
        # Extract number and unit
        if horizon.endswith('w'):
            weeks = int(horizon[:-1])
            return timedelta(weeks=weeks)
        elif horizon.endswith('m'):
            months = int(horizon[:-1])
            return timedelta(days=months * 30)  # approximate
        elif horizon.endswith('y'):
            years = int(horizon[:-1])
            return timedelta(days=years * 365)  # approximate
        elif horizon.endswith('d'):
            days = int(horizon[:-1])
            return timedelta(days=days)
        else:
            logger.warning(f"Unrecognized horizon format: {horizon_str}")
            return None
    except (ValueError, IndexError) as e:
        logger.warning(f"Failed to parse horizon '{horizon_str}': {e}")
        return None


# ── EVALUATE ONE PREDICTION ────────────────────────────────────────────────────

async def _evaluate_prediction(
    prediction: PredictionRecord,
    db: AsyncSession,
) -> bool:
    """
    Evaluate a single prediction by fetching current data and comparing.
    Returns True if evaluation succeeded, False if it should be retried later.
    """
    ticker = prediction.ticker
    
    # Fetch current market snapshot
    snapshot = await fetch_market_snapshot(ticker)
    
    if snapshot.current_price is None:
        logger.warning(
            f"Cannot evaluate prediction {prediction.id[:8]}... — "
            f"no price data for {ticker}. Will retry later."
        )
        return False  # Don't mark as evaluated, try again next run
    
    # Get original price from analysis_context
    original_price = None
    if prediction.analysis_context and 'market_price' in prediction.analysis_context:
        original_price = prediction.analysis_context['market_price']
    
    if original_price is None:
        logger.error(
            f"Cannot evaluate prediction {prediction.id[:8]}... — "
            f"no original price in analysis_context"
        )
        # Mark as FAILED rather than leaving PENDING
        await db.execute(
            update(PredictionRecord)
            .where(PredictionRecord.id == prediction.id)
            .values(evaluation_status='FAILED')
        )
        return True  # Don't retry
    
    current_price = snapshot.current_price
    
    # ── CALCULATE METRICS ──────────────────────────────────────
    actual_return_pct = ((current_price - original_price) / original_price) * 100
    
    # Determine if direction was correct
    predicted_up = prediction.predicted_direction in ['buy', 'long', 'bullish']
    actual_up = actual_return_pct > 0
    direction_correct = (predicted_up == actual_up)
    
    # Calculate absolute error (if predicted_return_pct was provided)
    absolute_error = None
    if prediction.predicted_return_pct is not None:
        absolute_error = abs(actual_return_pct - prediction.predicted_return_pct)
    
    # Simple accuracy score: 1.0 if direction correct, 0.0 if not
    # (More sophisticated scoring could weight by confidence, magnitude, etc.)
    accuracy_score = 1.0 if direction_correct else 0.0
    
    # ── CREATE OUTCOME RECORD ──────────────────────────────────
    outcome = PredictionOutcome(
        prediction_id=prediction.id,
        evaluation_timestamp=datetime.utcnow(),
        actual_price_start=original_price,
        actual_price_end=current_price,
        actual_return_pct=actual_return_pct,
        is_direction_correct=direction_correct,
        absolute_error=absolute_error if absolute_error is not None else 0.0,
        prediction_accuracy_score=accuracy_score,
        evaluation_status='COMPLETED',
    )
    
    db.add(outcome)
    
    # ── UPDATE PREDICTION STATUS ───────────────────────────────
    await db.execute(
        update(PredictionRecord)
        .where(PredictionRecord.id == prediction.id)
        .values(evaluation_status='EVALUATED')
    )
    
    await db.commit()
    
    logger.info(
        f"✓ Evaluated prediction {prediction.id[:8]}... | {ticker} | "
        f"predicted={prediction.predicted_direction} "
        f"actual_return={actual_return_pct:.2f}% "
        f"direction_correct={direction_correct} "
        f"accuracy={accuracy_score:.2f}"
    )
    
    return True


# ── MAIN EVALUATOR RUN ─────────────────────────────────────────────────────────

async def run_prediction_evaluator() -> None:
    """
    Find and evaluate all predictions that are ready for evaluation.
    Called by the scheduler (typically every 24 hours).
    
    A prediction is ready when:
    - evaluation_due_at <= now
    - evaluation_status = 'PENDING'
    """
    async with AsyncSessionFactory() as db:
        now = datetime.utcnow()
        
        # Find predictions ready for evaluation
        result = await db.execute(
            select(PredictionRecord)
            .where(
                PredictionRecord.evaluation_due_at <= now,
                PredictionRecord.evaluation_status == 'PENDING'
            )
            .order_by(PredictionRecord.evaluation_due_at)
        )
        
        predictions = result.scalars().all()
        
        if not predictions:
            logger.debug("Prediction evaluator: no predictions ready for evaluation")
            return
        
        logger.info(
            f"Prediction evaluator: found {len(predictions)} predictions to evaluate"
        )
        
        evaluated = 0
        failed = 0
        
        for prediction in predictions:
            try:
                success = await _evaluate_prediction(prediction, db)
                if success:
                    evaluated += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(
                    f"Evaluation failed for prediction {prediction.id[:8]}... "
                    f"({prediction.ticker}): {e}"
                )
                failed += 1
        
        logger.info(
            f"Prediction evaluator complete: "
            f"{evaluated} evaluated, {failed} failed/deferred"
        )


# ── BACKFILL EVALUATION_DUE_AT ─────────────────────────────────────────────────

async def backfill_evaluation_due_dates() -> None:
    """
    One-time migration helper: set evaluation_due_at for existing predictions
    that don't have it set yet.
    
    Run this once after adding the evaluation_due_at column.
    """
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(PredictionRecord)
            .where(PredictionRecord.evaluation_due_at.is_(None))
        )
        
        predictions = result.scalars().all()
        
        if not predictions:
            logger.info("No predictions need evaluation_due_at backfill")
            return
        
        logger.info(f"Backfilling evaluation_due_at for {len(predictions)} predictions")
        
        for pred in predictions:
            horizon_delta = _parse_horizon(pred.prediction_horizon)
            if horizon_delta:
                pred.evaluation_due_at = pred.prediction_timestamp + horizon_delta
            else:
                # Default to 1 week if horizon unparseable
                pred.evaluation_due_at = pred.prediction_timestamp + timedelta(weeks=1)
        
        await db.commit()
        logger.info("Backfill complete")
