# =============================================================
# src/engine/prediction_evaluator.py
#
# Evaluates past predictions by comparing predicted vs actual
# market performance.
#
# V3 FIXES (post-audit):
#   1. Price is now fetched AS OF evaluation_due_at (horizon date),
#      not "whenever the evaluator happens to run". Late evaluation
#      no longer corrupts returns.
#   2. Uses yf_client_v2 ticker resolution so forex/commodity/crypto
#      tickers (USDCHF, GOLD, BTC) resolve correctly.
#   3. HOLD is graded within a tolerance band (±3% default) instead
#      of being treated as a bearish directional bet.
#   4. Guards against near-zero elapsed time: if the prediction is
#      younger than MIN_ELAPSED_HOURS, evaluation is deferred even
#      if evaluation_due_at is (incorrectly) in the past.
#   5. CHECKPOINTS: a long-horizon call (e.g. 5y) would not be graded
#      for years, so calibration would never see it. Each one gets a
#      companion 1m "checkpoint" record — same ticker, direction and
#      raw confidence — graded a month after the call was made.
# =============================================================

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional

import yfinance as yf
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import new_uuid
from src.db.v3_models import PredictionRecord, PredictionOutcome
from src.db.session import AsyncSessionFactory
from src.ingestion.asset_registry import resolve_ticker

_thread_pool = ThreadPoolExecutor(max_workers=2)

# HOLD is "correct" if |actual return| stays inside this band
HOLD_TOLERANCE_PCT = 3.0

# Never evaluate a prediction younger than this, even if due_at says so.
# Protects against bad seed data / backfill errors producing 0.00% returns.
MIN_ELAPSED_HOURS = 24

# Predictions with a longer horizon than this get a checkpoint record
CHECKPOINT_HORIZON = '1m'
CHECKPOINT_DELTA = timedelta(days=30)


# ── HORIZON PARSING ────────────────────────────────────────────────────────────

def _parse_horizon(horizon_str: str) -> Optional[timedelta]:
    """'1w'→7d, '1m'→30d, '3m'→90d, '1y'→365d, '5d'→5d. None if unparseable."""
    if not horizon_str:
        return None
    try:
        horizon = horizon_str.strip().lower()
        if horizon.endswith('w'):
            return timedelta(weeks=int(horizon[:-1]))
        elif horizon.endswith('m'):
            return timedelta(days=int(horizon[:-1]) * 30)
        elif horizon.endswith('y'):
            return timedelta(days=int(horizon[:-1]) * 365)
        elif horizon.endswith('d'):
            return timedelta(days=int(horizon[:-1]))
        logger.warning(f"Unrecognized horizon format: {horizon_str}")
        return None
    except (ValueError, IndexError) as e:
        logger.warning(f"Failed to parse horizon '{horizon_str}': {e}")
        return None


# ── GRADING ────────────────────────────────────────────────────────────────────

def grade_direction(direction: str, actual_return_pct: float) -> bool:
    """
    Was the call right? Shared with backtester.py so live and
    historical accuracy are graded identically.
    
    HOLD/neutral is a non-directional call: correct if the price
    stayed inside ±HOLD_TOLERANCE_PCT.
    """
    direction = (direction or '').lower()
    if direction in ('hold', 'neutral'):
        return abs(actual_return_pct) <= HOLD_TOLERANCE_PCT
    if direction in ('buy', 'long', 'bullish'):
        return actual_return_pct > 0
    # avoid / sell / short / bearish
    return actual_return_pct < 0


# ── PRICE AS OF A SPECIFIC DATE ────────────────────────────────────────────────

def _fetch_price_asof_sync(ticker: str, target_date: datetime) -> Optional[float]:
    """
    Fetch the closing price for `ticker` at the trading day closest to
    (and not after) target_date. Resolves through the multi-asset registry
    so forex/commodity/crypto tickers work.
    """
    try:
        yf_symbol, _asset_class, _meta = resolve_ticker(ticker)
        ticker_obj = yf.Ticker(yf_symbol)

        start = target_date - timedelta(days=10)
        end = target_date + timedelta(days=2)
        hist = ticker_obj.history(start=start, end=end)

        if hist.empty:
            return None

        # Closest trading day on or before target_date
        valid = hist.index[hist.index.date <= target_date.date()]
        if len(valid) == 0:
            valid = hist.index
        return float(hist.loc[valid[-1], 'Close'])
    except Exception as e:
        logger.error(f"Price fetch failed for {ticker} asof {target_date.date()}: {e}")
        return None


async def _fetch_price_asof(ticker: str, target_date: datetime) -> Optional[float]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _thread_pool, _fetch_price_asof_sync, ticker, target_date
    )


# ── EVALUATE ONE PREDICTION ────────────────────────────────────────────────────

async def _evaluate_prediction(
    prediction: PredictionRecord,
    db: AsyncSession,
) -> bool:
    """
    Evaluate a single prediction. Returns True if handled (evaluated or
    permanently failed), False if it should be retried on a later run.
    """
    ticker = prediction.ticker
    now = datetime.utcnow()

    # ── SANITY GUARD: minimum elapsed time ─────────────────────
    elapsed = now - prediction.prediction_timestamp
    if elapsed < timedelta(hours=MIN_ELAPSED_HOURS):
        logger.warning(
            f"Prediction {prediction.id[:8]}... ({ticker}) is only "
            f"{elapsed.total_seconds()/3600:.1f}h old but marked due — "
            f"deferring. Check evaluation_due_at integrity."
        )
        return False

    # ── ORIGINAL PRICE ─────────────────────────────────────────
    original_price = None
    if prediction.analysis_context and 'market_price' in prediction.analysis_context:
        original_price = prediction.analysis_context['market_price']

    if original_price is None or original_price <= 0:
        logger.error(
            f"Prediction {prediction.id[:8]}... ({ticker}) has no valid "
            f"original price — marking FAILED"
        )
        await db.execute(
            update(PredictionRecord)
            .where(PredictionRecord.id == prediction.id)
            .values(evaluation_status='FAILED')
        )
        await db.commit()
        return True

    # ── PRICE AT HORIZON DATE (not "now") ──────────────────────
    # Anchor the outcome to evaluation_due_at so late evaluator runs
    # don't grade a 1-week call against a 5-week outcome.
    horizon_date = prediction.evaluation_due_at or now
    price_at_horizon = await _fetch_price_asof(ticker, horizon_date)

    if price_at_horizon is None:
        logger.warning(
            f"Cannot evaluate {prediction.id[:8]}... — no price data for "
            f"{ticker} asof {horizon_date.date()}. Will retry."
        )
        return False

    # ── METRICS ────────────────────────────────────────────────
    actual_return_pct = ((price_at_horizon - original_price) / original_price) * 100

    direction = (prediction.predicted_direction or '').lower()
    direction_correct = grade_direction(direction, actual_return_pct)

    absolute_error = None
    if prediction.predicted_return_pct is not None:
        absolute_error = abs(actual_return_pct - prediction.predicted_return_pct)

    accuracy_score = 1.0 if direction_correct else 0.0

    outcome = PredictionOutcome(
        prediction_id=prediction.id,
        evaluation_timestamp=now,
        actual_price_start=original_price,
        actual_price_end=price_at_horizon,
        actual_return_pct=actual_return_pct,
        is_direction_correct=direction_correct,
        absolute_error=absolute_error,
        prediction_accuracy_score=accuracy_score,
        evaluation_status='COMPLETED',
    )
    db.add(outcome)

    await db.execute(
        update(PredictionRecord)
        .where(PredictionRecord.id == prediction.id)
        .values(evaluation_status='EVALUATED')
    )
    await db.commit()

    logger.info(
        f"✓ Evaluated {prediction.id[:8]}... | {ticker} | "
        f"{direction} | start={original_price:.4f} "
        f"end={price_at_horizon:.4f} return={actual_return_pct:+.2f}% "
        f"correct={direction_correct}"
    )
    return True


# ── MAIN EVALUATOR RUN ─────────────────────────────────────────────────────────

async def run_prediction_evaluator() -> None:
    """Evaluate all predictions whose horizon has elapsed. Runs every 24h."""
    async with AsyncSessionFactory() as db:
        now = datetime.utcnow()

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
            logger.debug("Prediction evaluator: nothing ready")
            return

        logger.info(f"Prediction evaluator: {len(predictions)} predictions due")

        evaluated = deferred = 0
        for prediction in predictions:
            try:
                if await _evaluate_prediction(prediction, db):
                    evaluated += 1
                else:
                    deferred += 1
            except Exception as e:
                logger.error(
                    f"Evaluation error for {prediction.id[:8]}... "
                    f"({prediction.ticker}): {e}"
                )
                deferred += 1

        logger.info(
            f"Prediction evaluator complete: {evaluated} handled, {deferred} deferred"
        )


# ── BACKFILL EVALUATION_DUE_AT ─────────────────────────────────────────────────

async def backfill_evaluation_due_dates() -> None:
    """Set evaluation_due_at where missing, from prediction_timestamp + horizon."""
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(PredictionRecord)
            .where(PredictionRecord.evaluation_due_at.is_(None))
        )
        predictions = result.scalars().all()
        if not predictions:
            logger.info("No predictions need evaluation_due_at backfill")
            return

        logger.info(f"Backfilling evaluation_due_at for {len(predictions)}")
        for pred in predictions:
            delta = _parse_horizon(pred.prediction_horizon) or timedelta(weeks=1)
            pred.evaluation_due_at = pred.prediction_timestamp + delta
        await db.commit()
        logger.info("Backfill complete")


# ── CHECKPOINT PREDICTIONS ─────────────────────────────────────────────────────

def make_checkpoint_prediction(parent: PredictionRecord) -> Optional[PredictionRecord]:
    """
    Build a 1m checkpoint copy of a long-horizon prediction, or None if
    the parent's horizon is already CHECKPOINT_DELTA or shorter.

    The checkpoint keeps the parent's timestamp, so its outcome is the
    price move in the month after the call was actually made.
    """
    delta = _parse_horizon(parent.prediction_horizon)
    if delta is None or delta <= CHECKPOINT_DELTA:
        return None

    if parent.id is None:
        parent.id = new_uuid()

    return PredictionRecord(
        ticker=parent.ticker,
        prediction_timestamp=parent.prediction_timestamp,
        prediction_horizon=CHECKPOINT_HORIZON,
        predicted_direction=parent.predicted_direction,
        predicted_return_pct=None,
        confidence_score=parent.confidence_score,
        raw_confidence=parent.raw_confidence,
        analysis_context={
            **(parent.analysis_context or {}),
            'checkpoint_of': parent.id,
            'checkpoint_parent_horizon': parent.prediction_horizon,
        },
        prompt_version=parent.prompt_version,
        model_version=parent.model_version,
        sector=parent.sector,
        asset_class=parent.asset_class,
        evaluation_status='PENDING',
        evaluation_due_at=parent.prediction_timestamp + CHECKPOINT_DELTA,
    )


async def backfill_checkpoint_predictions() -> int:
    """
    Create checkpoints for existing long-horizon predictions that don't
    have one yet. Returns the number created. Safe to re-run.
    """
    async with AsyncSessionFactory() as db:
        result = await db.execute(select(PredictionRecord))
        predictions = result.scalars().all()

        has_checkpoint = {
            (p.analysis_context or {}).get('checkpoint_of')
            for p in predictions
        }
        created = 0
        for parent in predictions:
            if parent.id in has_checkpoint or 'checkpoint_of' in (parent.analysis_context or {}):
                continue
            checkpoint = make_checkpoint_prediction(parent)
            if checkpoint is not None:
                db.add(checkpoint)
                created += 1
        await db.commit()

    logger.info(f"Checkpoint backfill: created {created} checkpoint predictions")
    return created
