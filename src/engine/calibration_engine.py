# =============================================================
# src/engine/calibration_engine.py
#
# FinTrac V3 — Phase 5: Self-Calibration Engine
#
# WHAT THIS DOES:
# Analyzes all evaluated predictions to detect systematic biases
# in the AI's analysis, computes correction factors, and stores
# CalibrationProfile records that the agent uses to adjust future
# predictions.
#
# BIAS TYPES DETECTED:
#   1. OPTIMISM_BIAS        — AI predicts BUY too often; assets decline
#   2. PESSIMISM_BIAS       — AI predicts AVOID too often; assets rise
#   3. OVERCONFIDENCE       — High confidence but low accuracy
#   4. SECTOR_BLINDNESS     — Consistently wrong on specific sectors
#   5. VOLATILITY_UNDEREST  — Misses large price swings
#   6. DIRECTION_BIAS       — Always predicting same direction
#
# MINIMUM SAMPLE SIZE:
# No calibration profile is created unless there are at least
# MIN_SAMPLE_SIZE evaluated predictions for that sector/class.
# Calibrating on 3 predictions is noise, not signal.
#
# CORRECTION FACTORS:
# Multiplicative adjustment for future confidence scores:
#   adjusted_confidence = raw_confidence * correction_factor
# If the AI is overconfident in Tech (0.85 avg confidence but
# only 55% accuracy), correction_factor < 1.0 pulls it down.
#
# CALLED BY: scheduler.py every 7 days (after prediction evaluator)
# =============================================================

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.v3_models import (
    PredictionRecord,
    PredictionOutcome,
    CalibrationProfile,
)
from src.db.session import AsyncSessionFactory


# ── CONFIGURATION ──────────────────────────────────────────────────────────────

MIN_SAMPLE_SIZE = 10          # Minimum predictions to create a calibration profile
OVERCONFIDENCE_THRESHOLD = 15  # If accuracy is 15%+ below avg confidence, flag it
BIAS_THRESHOLD = 0.15         # 15% imbalance triggers a bias detection
VOLATILITY_THRESHOLD = 10.0   # If avg absolute error > 10%, flag volatility underestimation


# ── HELPER: COMPUTE BASIC STATS ───────────────────────────────────────────────

def _compute_accuracy_stats(
    predictions: List[dict],
) -> dict:
    """
    Compute accuracy and confidence stats from a list of prediction dicts.
    
    Each dict has: predicted_direction, confidence, is_correct, actual_return_pct
    
    Returns dict with:
        total, correct, accuracy_pct, avg_confidence, avg_actual_return,
        buy_count, avoid_count, hold_count, direction_correct_pct,
        avg_absolute_return, max_absolute_return
    """
    total = len(predictions)
    if total == 0:
        return {'total': 0}
    
    correct = sum(1 for p in predictions if p['is_correct'])
    accuracy_pct = (correct / total) * 100
    
    avg_confidence = sum(p['confidence'] for p in predictions) / total
    avg_actual_return = sum(p['actual_return_pct'] for p in predictions) / total
    
    # Direction distribution
    buy_count = sum(1 for p in predictions if p['predicted_direction'] in ('buy', 'long', 'bullish'))
    avoid_count = sum(1 for p in predictions if p['predicted_direction'] in ('avoid', 'short', 'bearish'))
    hold_count = total - buy_count - avoid_count
    
    # Volatility stats
    absolute_returns = [abs(p['actual_return_pct']) for p in predictions]
    avg_absolute_return = sum(absolute_returns) / total
    max_absolute_return = max(absolute_returns) if absolute_returns else 0
    
    # Overconfidence: gap between confidence and accuracy
    confidence_accuracy_gap = (avg_confidence * 100) - accuracy_pct
    
    return {
        'total': total,
        'correct': correct,
        'accuracy_pct': round(accuracy_pct, 1),
        'avg_confidence': round(avg_confidence, 3),
        'avg_confidence_pct': round(avg_confidence * 100, 1),
        'avg_actual_return': round(avg_actual_return, 2),
        'buy_count': buy_count,
        'avoid_count': avoid_count,
        'hold_count': hold_count,
        'buy_pct': round((buy_count / total) * 100, 1),
        'avoid_pct': round((avoid_count / total) * 100, 1),
        'avg_absolute_return': round(avg_absolute_return, 2),
        'max_absolute_return': round(max_absolute_return, 2),
        'confidence_accuracy_gap': round(confidence_accuracy_gap, 1),
    }


# ── BIAS DETECTORS ─────────────────────────────────────────────────────────────

def _detect_optimism_bias(stats: dict) -> Optional[Tuple[float, float]]:
    """
    Detect if AI is overly bullish — predicts BUY too often, assets decline.
    
    Returns (bias_magnitude, correction_factor) or None.
    """
    if stats['total'] < MIN_SAMPLE_SIZE:
        return None
    
    # Check if BUY predictions dominate AND accuracy is low
    buy_ratio = stats['buy_pct'] / 100
    
    if buy_ratio > (0.5 + BIAS_THRESHOLD):
        # AI is biased toward BUY
        # How wrong is it? Compare accuracy of BUY predictions specifically
        # If overall accuracy is below 50%, the optimism is costing us
        if stats['accuracy_pct'] < 55:
            magnitude = buy_ratio - 0.5  # How far above 50% BUY we are
            # Correction: reduce confidence on BUY predictions
            correction = max(0.7, 1.0 - (magnitude * 0.5))
            return (round(magnitude, 3), round(correction, 3))
    
    return None


def _detect_pessimism_bias(stats: dict) -> Optional[Tuple[float, float]]:
    """
    Detect if AI is overly bearish — predicts AVOID too often, assets rise.
    
    Returns (bias_magnitude, correction_factor) or None.
    """
    if stats['total'] < MIN_SAMPLE_SIZE:
        return None
    
    avoid_ratio = stats['avoid_pct'] / 100
    
    if avoid_ratio > (0.5 + BIAS_THRESHOLD):
        if stats['accuracy_pct'] < 55:
            magnitude = avoid_ratio - 0.5
            correction = max(0.7, 1.0 - (magnitude * 0.5))
            return (round(magnitude, 3), round(correction, 3))
    
    return None


def _detect_overconfidence(stats: dict) -> Optional[Tuple[float, float]]:
    """
    Detect if AI confidence scores don't match actual accuracy.
    
    If avg confidence is 85% but accuracy is 55%, the AI is overconfident.
    
    Returns (bias_magnitude, correction_factor) or None.
    """
    if stats['total'] < MIN_SAMPLE_SIZE:
        return None
    
    gap = stats['confidence_accuracy_gap']
    
    if gap > OVERCONFIDENCE_THRESHOLD:
        # Confidence exceeds accuracy by more than threshold
        magnitude = gap / 100  # Normalize to 0-1 scale
        # Correction: scale confidence down toward actual accuracy
        # If accuracy=55%, confidence=85%, we want to pull confidence toward 55%
        if stats['avg_confidence_pct'] > 0:
            correction = stats['accuracy_pct'] / stats['avg_confidence_pct']
            correction = max(0.5, min(1.0, correction))  # Clamp to 0.5-1.0
        else:
            correction = 0.8
        return (round(magnitude, 3), round(correction, 3))
    
    return None


def _detect_volatility_underestimation(stats: dict) -> Optional[Tuple[float, float]]:
    """
    Detect if AI misses large price swings.
    
    If the average absolute return is high but accuracy is low,
    the AI is not accounting for volatility.
    
    Returns (bias_magnitude, correction_factor) or None.
    """
    if stats['total'] < MIN_SAMPLE_SIZE:
        return None
    
    if stats['avg_absolute_return'] > VOLATILITY_THRESHOLD and stats['accuracy_pct'] < 55:
        magnitude = stats['avg_absolute_return'] / 100  # Normalize
        # Correction: reduce confidence in volatile sectors
        correction = max(0.6, 1.0 - (magnitude * 0.3))
        return (round(magnitude, 3), round(correction, 3))
    
    return None


def _detect_direction_bias(stats: dict) -> Optional[Tuple[float, float]]:
    """
    Detect if AI always predicts the same direction regardless of conditions.
    
    If 80%+ of predictions are BUY or 80%+ are AVOID, the AI isn't
    differentiating between assets.
    
    Returns (bias_magnitude, correction_factor) or None.
    """
    if stats['total'] < MIN_SAMPLE_SIZE:
        return None
    
    max_direction_pct = max(stats['buy_pct'], stats['avoid_pct'])
    
    if max_direction_pct > 80:
        magnitude = (max_direction_pct - 50) / 100
        correction = max(0.7, 1.0 - (magnitude * 0.4))
        return (round(magnitude, 3), round(correction, 3))
    
    return None


# ── CORE: ANALYZE AND WRITE PROFILES ──────────────────────────────────────────

async def _fetch_evaluated_predictions(db: AsyncSession) -> List[dict]:
    """
    Fetch all evaluated predictions with their outcomes.
    Returns a list of dicts with merged prediction + outcome data.
    """
    result = await db.execute(
        select(
            PredictionRecord.id,
            PredictionRecord.ticker,
            PredictionRecord.sector,
            PredictionRecord.asset_class,
            PredictionRecord.predicted_direction,
            PredictionRecord.confidence_score,
            PredictionRecord.prediction_timestamp,
            PredictionOutcome.actual_return_pct,
            PredictionOutcome.is_direction_correct,
            PredictionOutcome.absolute_error,
        )
        .join(PredictionOutcome, PredictionRecord.id == PredictionOutcome.prediction_id)
        .where(PredictionRecord.evaluation_status == 'EVALUATED')
    )
    
    predictions = []
    for row in result:
        predictions.append({
            'id': row.id,
            'ticker': row.ticker,
            'sector': row.sector or 'Unknown',
            'asset_class': row.asset_class or 'EQUITY',
            'predicted_direction': row.predicted_direction,
            'confidence': row.confidence_score,
            'prediction_timestamp': row.prediction_timestamp,
            'actual_return_pct': row.actual_return_pct,
            'is_correct': bool(row.is_direction_correct),
            'absolute_error': row.absolute_error,
        })
    
    return predictions


async def _deactivate_old_profiles(db: AsyncSession) -> int:
    """
    Mark all existing active profiles as inactive before writing new ones.
    Calibration is always computed fresh from the full dataset.
    Returns number of profiles deactivated.
    """
    from sqlalchemy import update
    
    result = await db.execute(
        update(CalibrationProfile)
        .where(CalibrationProfile.active == True)
        .values(active=False)
    )
    
    return result.rowcount


async def _write_profile(
    db: AsyncSession,
    sector: Optional[str],
    asset_class: Optional[str],
    bias_type: str,
    magnitude: float,
    correction_factor: float,
    sample_size: int,
    confidence_interval: Optional[dict] = None,
) -> CalibrationProfile:
    """
    Create a new CalibrationProfile record.
    """
    profile = CalibrationProfile(
        sector=sector,
        asset_class=asset_class,
        bias_type=bias_type,
        detected_at=datetime.utcnow(),
        sample_size=sample_size,
        bias_magnitude=magnitude,
        correction_factor=correction_factor,
        active=True,
        confidence_interval=confidence_interval,
    )
    
    db.add(profile)
    return profile


def _run_bias_detectors(stats: dict) -> List[Tuple[str, float, float]]:
    """
    Run all bias detectors on a stats dict.
    Returns list of (bias_type, magnitude, correction_factor).
    """
    detected = []
    
    detectors = [
        ('OPTIMISM_BIAS', _detect_optimism_bias),
        ('PESSIMISM_BIAS', _detect_pessimism_bias),
        ('OVERCONFIDENCE', _detect_overconfidence),
        ('VOLATILITY_UNDERESTIMATION', _detect_volatility_underestimation),
        ('DIRECTION_BIAS', _detect_direction_bias),
    ]
    
    for bias_type, detector in detectors:
        result = detector(stats)
        if result is not None:
            magnitude, correction = result
            detected.append((bias_type, magnitude, correction))
    
    return detected


# ── PUBLIC: RUN CALIBRATION ───────────────────────────────────────────────────

async def run_calibration_engine() -> dict:
    """
    Main entry point. Analyzes all evaluated predictions,
    detects biases, and writes CalibrationProfile records.
    
    Called by scheduler.py every 7 days.
    
    Returns statistics about the calibration run.
    """
    logger.info("═══ CALIBRATION ENGINE: Starting calibration run ═══")
    
    async with AsyncSessionFactory() as db:
        # ── FETCH ALL EVALUATED PREDICTIONS ────────────────────
        all_predictions = await _fetch_evaluated_predictions(db)
        
        if not all_predictions:
            logger.info("No evaluated predictions found. Calibration skipped.")
            return {
                'status': 'skipped',
                'reason': 'no_evaluated_predictions',
                'profiles_created': 0,
            }
        
        logger.info(f"Loaded {len(all_predictions)} evaluated predictions")
        
        # ── DEACTIVATE OLD PROFILES ────────────────────────────
        deactivated = await _deactivate_old_profiles(db)
        if deactivated > 0:
            logger.info(f"Deactivated {deactivated} old calibration profiles")
        
        profiles_created = 0
        biases_detected = []
        
        # ── GLOBAL ANALYSIS ────────────────────────────────────
        # Run bias detectors on the full dataset
        global_stats = _compute_accuracy_stats(all_predictions)
        logger.info(
            f"Global stats: {global_stats['total']} predictions, "
            f"{global_stats['accuracy_pct']}% accuracy, "
            f"{global_stats['avg_confidence_pct']}% avg confidence"
        )
        
        global_biases = _run_bias_detectors(global_stats)
        for bias_type, magnitude, correction in global_biases:
            await _write_profile(
                db,
                sector=None,           # Global = applies to all
                asset_class=None,
                bias_type=bias_type,
                magnitude=magnitude,
                correction_factor=correction,
                sample_size=global_stats['total'],
                confidence_interval={
                    'accuracy_pct': global_stats['accuracy_pct'],
                    'avg_confidence_pct': global_stats['avg_confidence_pct'],
                    'scope': 'global',
                },
            )
            profiles_created += 1
            biases_detected.append({
                'scope': 'GLOBAL',
                'bias': bias_type,
                'magnitude': magnitude,
                'correction': correction,
            })
            logger.warning(
                f"GLOBAL BIAS DETECTED: {bias_type} "
                f"(magnitude={magnitude}, correction={correction})"
            )
        
        # ── PER-SECTOR ANALYSIS ────────────────────────────────
        sectors: Dict[str, List[dict]] = {}
        for p in all_predictions:
            sectors.setdefault(p['sector'], []).append(p)
        
        for sector, preds in sectors.items():
            stats = _compute_accuracy_stats(preds)
            
            if stats['total'] < MIN_SAMPLE_SIZE:
                logger.debug(
                    f"Sector '{sector}' has {stats['total']} predictions "
                    f"(< {MIN_SAMPLE_SIZE}), skipping"
                )
                continue
            
            sector_biases = _run_bias_detectors(stats)
            for bias_type, magnitude, correction in sector_biases:
                await _write_profile(
                    db,
                    sector=sector,
                    asset_class=None,
                    bias_type=bias_type,
                    magnitude=magnitude,
                    correction_factor=correction,
                    sample_size=stats['total'],
                    confidence_interval={
                        'accuracy_pct': stats['accuracy_pct'],
                        'avg_confidence_pct': stats['avg_confidence_pct'],
                        'scope': 'sector',
                    },
                )
                profiles_created += 1
                biases_detected.append({
                    'scope': f'SECTOR:{sector}',
                    'bias': bias_type,
                    'magnitude': magnitude,
                    'correction': correction,
                })
                logger.warning(
                    f"SECTOR BIAS [{sector}]: {bias_type} "
                    f"(magnitude={magnitude}, correction={correction}, "
                    f"n={stats['total']}, accuracy={stats['accuracy_pct']}%)"
                )
        
        # ── PER-ASSET-CLASS ANALYSIS ───────────────────────────
        asset_classes: Dict[str, List[dict]] = {}
        for p in all_predictions:
            asset_classes.setdefault(p['asset_class'], []).append(p)
        
        for asset_class, preds in asset_classes.items():
            stats = _compute_accuracy_stats(preds)
            
            if stats['total'] < MIN_SAMPLE_SIZE:
                continue
            
            class_biases = _run_bias_detectors(stats)
            for bias_type, magnitude, correction in class_biases:
                await _write_profile(
                    db,
                    sector=None,
                    asset_class=asset_class,
                    bias_type=bias_type,
                    magnitude=magnitude,
                    correction_factor=correction,
                    sample_size=stats['total'],
                    confidence_interval={
                        'accuracy_pct': stats['accuracy_pct'],
                        'avg_confidence_pct': stats['avg_confidence_pct'],
                        'scope': 'asset_class',
                    },
                )
                profiles_created += 1
                biases_detected.append({
                    'scope': f'CLASS:{asset_class}',
                    'bias': bias_type,
                    'magnitude': magnitude,
                    'correction': correction,
                })
                logger.warning(
                    f"ASSET CLASS BIAS [{asset_class}]: {bias_type} "
                    f"(magnitude={magnitude}, correction={correction})"
                )
        
        # ── COMMIT ─────────────────────────────────────────────
        await db.commit()
        
        logger.info(
            f"═══ CALIBRATION COMPLETE: "
            f"{profiles_created} profiles created, "
            f"{len(biases_detected)} biases detected ═══"
        )
        
        return {
            'status': 'completed',
            'predictions_analyzed': len(all_predictions),
            'profiles_created': profiles_created,
            'profiles_deactivated': deactivated,
            'biases_detected': biases_detected,
            'global_accuracy_pct': global_stats['accuracy_pct'],
            'global_avg_confidence': global_stats['avg_confidence'],
        }


# ── PUBLIC: GET ACTIVE CALIBRATION FOR ASSET ──────────────────────────────────

async def get_calibration_context(
    sector: Optional[str],
    asset_class: Optional[str] = None,
) -> List[dict]:
    """
    Retrieve active calibration profiles relevant to a given sector/asset class.
    Used by advisor_agent.py to inject warnings into the AI prompt.
    
    Priority order:
      1. Sector-specific profiles
      2. Asset-class-specific profiles
      3. Global profiles (sector=None, asset_class=None)
    
    Returns list of dicts with bias_type, correction_factor, and context.
    """
    async with AsyncSessionFactory() as db:
        profiles = []
        
        # Sector-specific
        if sector:
            result = await db.execute(
                select(CalibrationProfile).where(
                    and_(
                        CalibrationProfile.active == True,
                        CalibrationProfile.sector == sector,
                    )
                )
            )
            for p in result.scalars().all():
                profiles.append({
                    'scope': f'sector:{p.sector}',
                    'bias_type': p.bias_type,
                    'correction_factor': p.correction_factor,
                    'magnitude': p.bias_magnitude,
                    'sample_size': p.sample_size,
                    'confidence_interval': p.confidence_interval,
                })
        
        # Asset-class-specific
        if asset_class:
            result = await db.execute(
                select(CalibrationProfile).where(
                    and_(
                        CalibrationProfile.active == True,
                        CalibrationProfile.asset_class == asset_class,
                    )
                )
            )
            for p in result.scalars().all():
                profiles.append({
                    'scope': f'class:{p.asset_class}',
                    'bias_type': p.bias_type,
                    'correction_factor': p.correction_factor,
                    'magnitude': p.bias_magnitude,
                    'sample_size': p.sample_size,
                    'confidence_interval': p.confidence_interval,
                })
        
        # Global profiles
        result = await db.execute(
            select(CalibrationProfile).where(
                and_(
                    CalibrationProfile.active == True,
                    CalibrationProfile.sector.is_(None),
                    CalibrationProfile.asset_class.is_(None),
                )
            )
        )
        for p in result.scalars().all():
            profiles.append({
                'scope': 'global',
                'bias_type': p.bias_type,
                'correction_factor': p.correction_factor,
                'magnitude': p.bias_magnitude,
                'sample_size': p.sample_size,
                'confidence_interval': p.confidence_interval,
            })
        
        return profiles


def format_calibration_for_prompt(profiles: List[dict]) -> str:
    """
    Format calibration profiles into a human-readable block
    for injection into the AI prompt.
    
    Returns empty string if no profiles, or a formatted warning block.
    """
    if not profiles:
        return ""
    
    lines = [
        "=== CALIBRATION WARNINGS (from self-evaluation) ===",
        "The following biases have been detected in your past analyses.",
        "Adjust your current analysis accordingly:\n",
    ]
    
    BIAS_DESCRIPTIONS = {
        'OPTIMISM_BIAS': (
            "You have historically predicted BUY too aggressively. "
            "Be more skeptical of bullish signals."
        ),
        'PESSIMISM_BIAS': (
            "You have historically been too bearish. "
            "Give more weight to positive catalysts."
        ),
        'OVERCONFIDENCE': (
            "Your confidence scores have been higher than your actual accuracy. "
            "Lower your confidence unless the evidence is overwhelming."
        ),
        'VOLATILITY_UNDERESTIMATION': (
            "You have underestimated price volatility. "
            "Widen your expected return range and flag volatility risks."
        ),
        'DIRECTION_BIAS': (
            "You tend to always predict the same direction. "
            "Evaluate each asset independently on its own merits."
        ),
    }
    
    for profile in profiles:
        bias = profile['bias_type']
        scope = profile['scope']
        ci = profile.get('confidence_interval', {})
        accuracy = ci.get('accuracy_pct', 'N/A')
        avg_conf = ci.get('avg_confidence_pct', 'N/A')
        
        description = BIAS_DESCRIPTIONS.get(bias, f"Bias detected: {bias}")
        
        lines.append(
            f"⚠ {bias} (scope: {scope}, n={profile['sample_size']}, "
            f"accuracy={accuracy}%, avg_confidence={avg_conf}%)"
        )
        lines.append(f"  → {description}")
        lines.append(
            f"  → Apply correction factor: {profile['correction_factor']} "
            f"to your confidence score.\n"
        )
    
    return "\n".join(lines)


# ── PUBLIC: APPLY CONFIDENCE CORRECTION ───────────────────────────────────────

def apply_confidence_correction(
    raw_confidence: float,
    profiles: List[dict],
) -> float:
    """
    Apply calibration correction factors to a raw confidence score.
    
    If multiple corrections apply (sector + global), they compound:
      adjusted = raw * correction_1 * correction_2
    
    Returns adjusted confidence clamped to [0.1, 1.0].
    """
    if not profiles:
        return raw_confidence
    
    adjusted = raw_confidence
    
    for profile in profiles:
        adjusted *= profile['correction_factor']
    
    # Clamp to valid range
    adjusted = max(0.1, min(1.0, adjusted))
    
    return round(adjusted, 3)
