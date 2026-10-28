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
#   1. OPTIMISM_BIAS        — mostly BUY, and BUY calls lose more often than win
#   2. PESSIMISM_BIAS       — mostly AVOID, and AVOID calls are wrong more often than right
#   3. OVERCONFIDENCE       — accuracy significantly below stated confidence
#   4. VOLATILITY_UNDEREST  — misses large price swings
#   5. DIRECTION_BIAS       — nearly always predicts the same direction
#   6. CONFIDENCE_MAP       — isotonic raw→calibrated confidence mapping
#                             (not a bias; the numeric correction itself)
#
# STATISTICAL GATES (see calibration_metrics.py):
#   - Predictions are de-duplicated per (ticker, day, horizon, direction).
#   - Every rate is tested with a 95% Wilson interval: a bias is only
#     flagged when the WHOLE interval is on the wrong side of the
#     threshold, not just the point estimate.
#   - Directional biases use per-action precision (BUY hit rate,
#     AVOID hit rate), not overall accuracy — HOLD is graded on a
#     ±band and would otherwise dilute them.
#   - HOLDOUT: candidates are detected on the oldest 70% of
#     predictions and only activated if their correction lowers the
#     Brier score on the newest 30%. The deployed factor/map is then
#     refit on all data.
#
# CORRECTION:
#   adjusted_confidence = CONFIDENCE_MAP(raw)            if a map is active
#                       = raw * min(bias factors)        otherwise
# Only the most specific scope available is used (sector > asset
# class > global). Factors are not compounded.
#
# Calibration is always computed on raw_confidence (the model's
# output BEFORE correction). Calibrating on corrected scores makes
# the engine learn from its own adjustments and oscillate.
#
# CALLED BY: scheduler.py every 7 days (after prediction evaluator)
# =============================================================

from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.v3_models import (
    PredictionRecord,
    PredictionOutcome,
    CalibrationProfile,
)
from src.db.session import AsyncSessionFactory
from src.engine.calibration_metrics import (
    apply_isotonic,
    brier_score,
    dedupe_predictions,
    expected_calibration_error,
    fit_isotonic,
    holdout_improvement,
    reliability_table,
    temporal_split,
    wilson_interval,
)


# ── CONFIGURATION ──────────────────────────────────────────────────────────────

MIN_SAMPLE_SIZE = 10           # Minimum predictions to consider a scope at all
MIN_HOLDOUT_SIZE = 5           # Minimum held-out predictions to validate a correction
MIN_ISOTONIC_SAMPLES = 30      # Isotonic maps need more data than a single factor
HOLDOUT_FRACTION = 0.3         # Newest 30% held out for validation
DIRECTION_SHARE = 0.65         # BUY/AVOID share above this is "mostly one way"
DIRECTION_BIAS_SHARE = 0.80    # Wilson LOWER bound above this is "always one way"
VOLATILITY_THRESHOLD = 10.0    # Avg absolute return (%) considered high-volatility
VOLATILITY_MAX_ACCURACY = 0.55 # ...and accuracy upper bound below this flags it

BUY_DIRECTIONS = ('buy', 'long', 'bullish')
AVOID_DIRECTIONS = ('avoid', 'sell', 'short', 'bearish')


# ── HELPER: COMPUTE BASIC STATS ───────────────────────────────────────────────

def _compute_accuracy_stats(
    predictions: List[dict],
) -> dict:
    """
    Compute accuracy, confidence and per-action stats from prediction dicts.

    Each dict has: predicted_direction, confidence, is_correct, actual_return_pct

    Rates are 0-1 floats here; *_pct fields are kept for the prompt and
    dashboard, which display percentages.
    """
    total = len(predictions)
    if total == 0:
        return {'total': 0}

    correct = sum(1 for p in predictions if p['is_correct'])
    avg_confidence = sum(p['confidence'] for p in predictions) / total
    avg_actual_return = sum(p['actual_return_pct'] for p in predictions) / total

    buys = [p for p in predictions if p['predicted_direction'] in BUY_DIRECTIONS]
    avoids = [p for p in predictions if p['predicted_direction'] in AVOID_DIRECTIONS]
    buy_correct = sum(1 for p in buys if p['is_correct'])
    avoid_correct = sum(1 for p in avoids if p['is_correct'])

    absolute_returns = [abs(p['actual_return_pct']) for p in predictions]
    accuracy = correct / total

    return {
        'total': total,
        'correct': correct,
        'accuracy': accuracy,
        'accuracy_ci': wilson_interval(correct, total),
        'accuracy_pct': round(accuracy * 100, 1),
        'avg_confidence': round(avg_confidence, 3),
        'avg_confidence_pct': round(avg_confidence * 100, 1),
        'avg_actual_return': round(avg_actual_return, 2),
        'buy_count': len(buys),
        'avoid_count': len(avoids),
        'hold_count': total - len(buys) - len(avoids),
        'buy_pct': round(len(buys) / total * 100, 1),
        'avoid_pct': round(len(avoids) / total * 100, 1),
        'buy_share_ci': wilson_interval(len(buys), total),
        'avoid_share_ci': wilson_interval(len(avoids), total),
        'buy_precision': (buy_correct / len(buys)) if buys else None,
        'buy_precision_ci': wilson_interval(buy_correct, len(buys)),
        'avoid_precision': (avoid_correct / len(avoids)) if avoids else None,
        'avoid_precision_ci': wilson_interval(avoid_correct, len(avoids)),
        # Base rate: how often the asset simply went up. A BUY hit rate
        # is only impressive relative to this.
        'up_rate': sum(1 for p in predictions if p['actual_return_pct'] > 0) / total,
        'avg_absolute_return': round(sum(absolute_returns) / total, 2),
        'max_absolute_return': round(max(absolute_returns), 2),
        'confidence_accuracy_gap': round((avg_confidence - accuracy) * 100, 1),
    }


# ── BIAS DETECTORS ─────────────────────────────────────────────────────────────
# Each returns (bias_magnitude, correction_factor) or None.
# A detector only fires when the 95% interval clears its threshold.

def _detect_optimism_bias(stats: dict) -> Optional[Tuple[float, float]]:
    """Mostly BUY, and BUY calls are significantly wrong more often than right."""
    if stats['total'] < MIN_SAMPLE_SIZE or not stats['buy_count']:
        return None

    buy_share = stats['buy_count'] / stats['total']
    if buy_share > DIRECTION_SHARE and stats['buy_precision_ci'][1] < 0.5:
        magnitude = buy_share - 0.5
        correction = max(0.7, 1.0 - (magnitude * 0.5))
        return (round(magnitude, 3), round(correction, 3))
    return None


def _detect_pessimism_bias(stats: dict) -> Optional[Tuple[float, float]]:
    """Mostly AVOID, and AVOID calls are significantly wrong more often than right."""
    if stats['total'] < MIN_SAMPLE_SIZE or not stats['avoid_count']:
        return None

    avoid_share = stats['avoid_count'] / stats['total']
    if avoid_share > DIRECTION_SHARE and stats['avoid_precision_ci'][1] < 0.5:
        magnitude = avoid_share - 0.5
        correction = max(0.7, 1.0 - (magnitude * 0.5))
        return (round(magnitude, 3), round(correction, 3))
    return None


def _detect_overconfidence(stats: dict) -> Optional[Tuple[float, float]]:
    """Even the optimistic end of the accuracy interval is below stated confidence."""
    if stats['total'] < MIN_SAMPLE_SIZE:
        return None

    accuracy_hi = stats['accuracy_ci'][1]
    if accuracy_hi < stats['avg_confidence']:
        magnitude = stats['avg_confidence'] - stats['accuracy']
        correction = stats['accuracy'] / stats['avg_confidence'] if stats['avg_confidence'] > 0 else 0.8
        correction = max(0.5, min(1.0, correction))
        return (round(magnitude, 3), round(correction, 3))
    return None


def _detect_volatility_underestimation(stats: dict) -> Optional[Tuple[float, float]]:
    """Large average moves and accuracy significantly below VOLATILITY_MAX_ACCURACY."""
    if stats['total'] < MIN_SAMPLE_SIZE:
        return None

    if (stats['avg_absolute_return'] > VOLATILITY_THRESHOLD
            and stats['accuracy_ci'][1] < VOLATILITY_MAX_ACCURACY):
        magnitude = stats['avg_absolute_return'] / 100
        correction = max(0.6, 1.0 - (magnitude * 0.3))
        return (round(magnitude, 3), round(correction, 3))
    return None


def _detect_direction_bias(stats: dict) -> Optional[Tuple[float, float]]:
    """Significantly more than DIRECTION_BIAS_SHARE of calls go the same way."""
    if stats['total'] < MIN_SAMPLE_SIZE:
        return None

    lower = max(stats['buy_share_ci'][0], stats['avoid_share_ci'][0])
    if lower > DIRECTION_BIAS_SHARE:
        share = max(stats['buy_count'], stats['avoid_count']) / stats['total']
        magnitude = share - 0.5
        correction = max(0.7, 1.0 - (magnitude * 0.4))
        return (round(magnitude, 3), round(correction, 3))
    return None


DETECTORS: List[Tuple[str, Callable[[dict], Optional[Tuple[float, float]]]]] = [
    ('OPTIMISM_BIAS', _detect_optimism_bias),
    ('PESSIMISM_BIAS', _detect_pessimism_bias),
    ('OVERCONFIDENCE', _detect_overconfidence),
    ('VOLATILITY_UNDERESTIMATION', _detect_volatility_underestimation),
    ('DIRECTION_BIAS', _detect_direction_bias),
]


def _run_bias_detectors(stats: dict) -> List[Tuple[str, float, float]]:
    """
    Run all bias detectors on a stats dict.
    Returns list of (bias_type, magnitude, correction_factor).
    """
    detected = []
    for bias_type, detector in DETECTORS:
        result = detector(stats)
        if result is not None:
            magnitude, correction = result
            detected.append((bias_type, magnitude, correction))
    return detected


# ── SCOPE CALIBRATION (pure — no DB) ──────────────────────────────────────────

def _round(x: Optional[float], digits: int = 4) -> Optional[float]:
    return None if x is None else round(x, digits)


def _scope_is_testable(predictions: List[dict]) -> bool:
    """Enough predictions to detect a bias AND validate it on a holdout."""
    if len(predictions) < MIN_SAMPLE_SIZE:
        return False
    _, holdout = temporal_split(predictions, HOLDOUT_FRACTION)
    return len(holdout) >= MIN_HOLDOUT_SIZE


def _calibrate_scope(predictions: List[dict]) -> List[dict]:
    """
    Detect biases for one scope (global / a sector / an asset class)
    and return the profiles that survive holdout validation.

    Each returned dict has: bias_type, magnitude, correction_factor,
    sample_size, details (stored as CalibrationProfile.confidence_interval).

    Expects predictions already de-duplicated.
    """
    if not _scope_is_testable(predictions):
        return []

    fit, holdout = temporal_split(predictions, HOLDOUT_FRACTION)

    confidences = [p['confidence'] for p in predictions]
    outcomes = [p['is_correct'] for p in predictions]
    fit_stats = _compute_accuracy_stats(fit)
    full_stats = _compute_accuracy_stats(predictions)
    full_detected = {b: (m, f) for b, m, f in _run_bias_detectors(full_stats)}

    base_details = {
        'accuracy_pct': full_stats['accuracy_pct'],
        'avg_confidence_pct': full_stats['avg_confidence_pct'],
        'accuracy_ci': [round(x, 3) for x in full_stats['accuracy_ci']],
        'brier': _round(brier_score(confidences, outcomes)),
        'ece': _round(expected_calibration_error(confidences, outcomes)),
        'holdout_n': len(holdout),
    }

    profiles = []

    # ── Scalar bias factors ──────────────────────────────────
    # Detect on the fit window, validate on holdout, then deploy the
    # factor computed on ALL data (only if the bias is still present).
    for bias_type, _fit_magnitude, fit_factor in _run_bias_detectors(fit_stats):
        brier_raw, brier_corrected = holdout_improvement(
            holdout, lambda c, f=fit_factor: max(0.1, min(1.0, c * f)),
        )
        if brier_corrected > brier_raw:
            logger.info(
                f"Calibration: {bias_type} rejected — holdout Brier "
                f"{brier_raw:.4f} → {brier_corrected:.4f} (no improvement)"
            )
            continue
        if bias_type not in full_detected:
            continue
        magnitude, factor = full_detected[bias_type]
        profiles.append({
            'bias_type': bias_type,
            'magnitude': magnitude,
            'correction_factor': factor,
            'sample_size': len(predictions),
            'details': {
                **base_details,
                'holdout_brier_raw': _round(brier_raw),
                'holdout_brier_corrected': _round(brier_corrected),
            },
        })

    # ── Isotonic confidence map ──────────────────────────────
    if len(predictions) >= MIN_ISOTONIC_SAMPLES:
        fit_map = fit_isotonic(
            [p['confidence'] for p in fit], [p['is_correct'] for p in fit],
        )
        brier_raw, brier_corrected = holdout_improvement(
            holdout, lambda c: apply_isotonic(c, fit_map),
        )
        if brier_corrected < brier_raw:
            full_map = fit_isotonic(confidences, outcomes)
            avg_raw = full_stats['avg_confidence']
            avg_mapped = sum(apply_isotonic(c, full_map) for c in confidences) / len(confidences)
            profiles.append({
                'bias_type': 'CONFIDENCE_MAP',
                'magnitude': round(abs(avg_raw - avg_mapped), 3),
                # Summary factor for display only; the map is what's applied
                'correction_factor': round(avg_mapped / avg_raw, 3) if avg_raw else 1.0,
                'sample_size': len(predictions),
                'details': {
                    **base_details,
                    'isotonic_map': full_map,
                    'holdout_brier_raw': _round(brier_raw),
                    'holdout_brier_corrected': _round(brier_corrected),
                },
            })
        else:
            logger.info(
                f"Calibration: isotonic map rejected — holdout Brier "
                f"{brier_raw:.4f} → {brier_corrected:.4f} (no improvement)"
            )

    return profiles


# ── REPORTING (pure — no DB) ──────────────────────────────────────────────────

def _rate(correct: int, n: int) -> dict:
    lo, hi = wilson_interval(correct, n)
    return {
        'n': n,
        'correct': correct,
        'rate': round(correct / n, 3) if n else None,
        'ci': [round(lo, 3), round(hi, 3)],
    }


def build_calibration_report(predictions: List[dict]) -> dict:
    """
    Calibration quality report for the dashboard.
    
    - raw:   the model's own confidence (what calibration learns from)
    - shown: the corrected confidence users actually saw
    Comparing their Brier scores shows whether correction is helping.
    """
    if not predictions:
        return {'n': 0}
    
    outcomes = [p['is_correct'] for p in predictions]
    raw = [p['confidence'] for p in predictions]
    shown = [p.get('shown_confidence', p['confidence']) for p in predictions]
    stats = _compute_accuracy_stats(predictions)
    
    by_action = {}
    for action, directions in (
        ('BUY', BUY_DIRECTIONS),
        ('AVOID', AVOID_DIRECTIONS),
        ('HOLD', ('hold', 'neutral')),
    ):
        group = [p for p in predictions if p['predicted_direction'] in directions]
        by_action[action] = _rate(sum(1 for p in group if p['is_correct']), len(group))
    
    by_horizon = {}
    for p in predictions:
        by_horizon.setdefault(p.get('prediction_horizon') or 'unknown', []).append(p)
    
    return {
        'n': len(predictions),
        'accuracy': _rate(stats['correct'], stats['total']),
        'brier_raw': _round(brier_score(raw, outcomes)),
        'brier_shown': _round(brier_score(shown, outcomes)),
        'ece_raw': _round(expected_calibration_error(raw, outcomes)),
        'ece_shown': _round(expected_calibration_error(shown, outcomes)),
        'reliability_raw': reliability_table(raw, outcomes),
        'by_action': by_action,
        # A BUY hit rate must beat this to show skill over "always BUY"
        'baseline_up_rate': round(stats['up_rate'], 3),
        'by_horizon': {
            h: _rate(sum(1 for p in group if p['is_correct']), len(group))
            for h, group in sorted(by_horizon.items())
        },
        'enough_data': len(predictions) >= MIN_SAMPLE_SIZE,
    }


# ── CORE: ANALYZE AND WRITE PROFILES ──────────────────────────────────────────

def _select_calibration_confidence(
    raw_confidence: Optional[float],
    stored_confidence: Optional[float],
    analysis_context: Optional[dict],
) -> Optional[float]:
    """
    Pick the confidence value to calibrate on.

    New rows carry raw_confidence. Legacy rows (before the column
    existed) only have the stored score, which is raw only if no
    calibration corrections were active when it was recorded.
    Returns None when the row can't be trusted for calibration.
    """
    if raw_confidence is not None:
        return raw_confidence

    corrections_active = (analysis_context or {}).get('calibration_corrections_active', 0)
    if corrections_active:
        return None
    return stored_confidence


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
            PredictionRecord.prediction_horizon,
            PredictionRecord.confidence_score,
            PredictionRecord.raw_confidence,
            PredictionRecord.analysis_context,
            PredictionRecord.prediction_timestamp,
            PredictionOutcome.actual_return_pct,
            PredictionOutcome.is_direction_correct,
            PredictionOutcome.absolute_error,
        )
        .join(PredictionOutcome, PredictionRecord.id == PredictionOutcome.prediction_id)
        .where(PredictionRecord.evaluation_status == 'EVALUATED')
    )

    predictions = []
    skipped = 0
    for row in result:
        confidence = _select_calibration_confidence(
            row.raw_confidence, row.confidence_score, row.analysis_context,
        )
        if confidence is None:
            skipped += 1
            continue
        predictions.append({
            'id': row.id,
            'ticker': row.ticker,
            'sector': row.sector or 'Unknown',
            'asset_class': row.asset_class or 'EQUITY',
            'predicted_direction': (row.predicted_direction or '').lower(),
            'prediction_horizon': row.prediction_horizon,
            'confidence': confidence,
            'shown_confidence': row.confidence_score,
            'prediction_timestamp': row.prediction_timestamp,
            'actual_return_pct': row.actual_return_pct,
            'is_correct': bool(row.is_direction_correct),
            'absolute_error': row.absolute_error,
        })

    if skipped:
        logger.info(
            f"Skipped {skipped} legacy predictions whose stored confidence "
            f"was already calibration-corrected (no raw_confidence)"
        )
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


def _profile_row(
    sector: Optional[str],
    asset_class: Optional[str],
    profile: dict,
) -> CalibrationProfile:
    """Build a CalibrationProfile record from a _calibrate_scope() result."""
    return CalibrationProfile(
        sector=sector,
        asset_class=asset_class,
        bias_type=profile['bias_type'],
        detected_at=datetime.utcnow(),
        sample_size=profile['sample_size'],
        bias_magnitude=profile['magnitude'],
        correction_factor=profile['correction_factor'],
        active=True,
        confidence_interval=profile['details'],
    )


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
        fetched = await _fetch_evaluated_predictions(db)
        all_predictions = dedupe_predictions(fetched)

        if not all_predictions:
            logger.info("No evaluated predictions found. Calibration skipped.")
            return {
                'status': 'skipped',
                'reason': 'no_evaluated_predictions',
                'profiles_created': 0,
            }

        logger.info(
            f"Loaded {len(fetched)} evaluated predictions "
            f"({len(all_predictions)} after de-duplication)"
        )

        # ── BUILD SCOPES ───────────────────────────────────────
        # (label, sector, asset_class, predictions)
        scopes: List[Tuple[str, Optional[str], Optional[str], List[dict]]] = [
            ('GLOBAL', None, None, all_predictions),
        ]
        sectors: Dict[str, List[dict]] = {}
        asset_classes: Dict[str, List[dict]] = {}
        for p in all_predictions:
            sectors.setdefault(p['sector'], []).append(p)
            asset_classes.setdefault(p['asset_class'], []).append(p)
        scopes += [(f'SECTOR:{s}', s, None, preds) for s, preds in sectors.items()]
        scopes += [(f'CLASS:{c}', None, c, preds) for c, preds in asset_classes.items()]

        new_rows: List[CalibrationProfile] = []
        biases_detected = []
        scopes_evaluated = 0

        for label, sector, asset_class, preds in scopes:
            if not _scope_is_testable(preds):
                logger.debug(
                    f"{label} has {len(preds)} predictions — too few to "
                    f"detect and holdout-validate a bias, skipping"
                )
                continue

            scopes_evaluated += 1
            for profile in _calibrate_scope(preds):
                new_rows.append(_profile_row(sector, asset_class, profile))
                biases_detected.append({
                    'scope': label,
                    'bias': profile['bias_type'],
                    'magnitude': profile['magnitude'],
                    'correction': profile['correction_factor'],
                })
                logger.warning(
                    f"{label} BIAS: {profile['bias_type']} "
                    f"(magnitude={profile['magnitude']}, "
                    f"correction={profile['correction_factor']}, "
                    f"n={profile['sample_size']})"
                )

        # ── REPLACE OLD PROFILES ───────────────────────────────
        # Only when at least one scope was actually tested. With too
        # little data the run can't confirm or refute existing
        # profiles, so they stay as they are.
        if scopes_evaluated == 0:
            logger.info(
                f"No scope has enough evaluated predictions to test "
                f"(have {len(all_predictions)}). Existing profiles kept."
            )
            return {
                'status': 'skipped',
                'reason': 'insufficient_evaluated_predictions',
                'predictions_analyzed': len(all_predictions),
                'profiles_created': 0,
            }

        deactivated = await _deactivate_old_profiles(db)
        if deactivated > 0:
            logger.info(f"Deactivated {deactivated} old calibration profiles")
        db.add_all(new_rows)
        profiles_created = len(new_rows)
        await db.commit()

        global_stats = _compute_accuracy_stats(all_predictions)
        logger.info(
            f"═══ CALIBRATION COMPLETE: "
            f"{profiles_created} profiles created, "
            f"{len(biases_detected)} biases detected ═══"
        )

        return {
            'status': 'completed',
            'predictions_analyzed': len(all_predictions),
            'duplicates_removed': len(fetched) - len(all_predictions),
            'profiles_created': profiles_created,
            'profiles_deactivated': deactivated,
            'biases_detected': biases_detected,
            'global_accuracy_pct': global_stats['accuracy_pct'],
            'global_avg_confidence': global_stats['avg_confidence'],
        }


# ── PUBLIC: GET ACTIVE CALIBRATION FOR ASSET ──────────────────────────────────

def _profile_dict(scope: str, p: CalibrationProfile) -> dict:
    return {
        'scope': scope,
        'bias_type': p.bias_type,
        'correction_factor': p.correction_factor,
        'magnitude': p.bias_magnitude,
        'sample_size': p.sample_size,
        'confidence_interval': p.confidence_interval,
    }


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
            profiles += [_profile_dict(f'sector:{p.sector}', p) for p in result.scalars().all()]

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
            profiles += [_profile_dict(f'class:{p.asset_class}', p) for p in result.scalars().all()]

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
        profiles += [_profile_dict('global', p) for p in result.scalars().all()]

        return profiles


def format_calibration_for_prompt(profiles: List[dict]) -> str:
    """
    Format calibration profiles into a human-readable block
    for injection into the AI prompt.

    Returns empty string if no profiles, or a formatted warning block.
    """
    # The confidence map is a numeric correction, not a behavioural bias
    profiles = [p for p in profiles if p['bias_type'] != 'CONFIDENCE_MAP']
    if not profiles:
        return ""

    lines = [
        "=== CALIBRATION WARNINGS (from self-evaluation) ===",
        "The following biases have been detected in your past analyses.",
        "Adjust your reasoning accordingly, but report your honest, unadjusted",
        "confidence — a numeric correction is applied automatically afterwards.\n",
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
            "Scrutinise weak or one-sided evidence before committing to a call."
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
        ci = profile.get('confidence_interval') or {}
        accuracy = ci.get('accuracy_pct', 'N/A')
        avg_conf = ci.get('avg_confidence_pct', 'N/A')

        description = BIAS_DESCRIPTIONS.get(bias, f"Bias detected: {bias}")

        lines.append(
            f"⚠ {bias} (scope: {scope}, n={profile['sample_size']}, "
            f"accuracy={accuracy}%, avg_confidence={avg_conf}%)"
        )
        lines.append(f"  → {description}\n")

    return "\n".join(lines)


# ── PUBLIC: APPLY CONFIDENCE CORRECTION ───────────────────────────────────────

def apply_confidence_correction(
    raw_confidence: float,
    profiles: List[dict],
) -> float:
    """
    Apply calibration correction to a raw confidence score.

    Uses only the most specific scope that has profiles
    (sector > asset class > global). Within it:
      - if a CONFIDENCE_MAP is active, the isotonic map is applied
      - otherwise the strongest single bias factor:
          adjusted = raw * min(correction factors in that scope)

    Returns adjusted confidence clamped to [0.1, 1.0].
    """
    if not profiles:
        return raw_confidence

    for prefix in ('sector:', 'class:', 'global'):
        scoped = [p for p in profiles if p['scope'].startswith(prefix)]
        if scoped:
            break
    else:
        return raw_confidence

    maps = [
        (p.get('confidence_interval') or {}).get('isotonic_map')
        for p in scoped if p['bias_type'] == 'CONFIDENCE_MAP'
    ]
    maps = [m for m in maps if m]
    if maps:
        adjusted = apply_isotonic(raw_confidence, maps[0])
    else:
        factors = [p['correction_factor'] for p in scoped if p['bias_type'] != 'CONFIDENCE_MAP']
        if not factors:
            return raw_confidence
        adjusted = raw_confidence * min(factors)

    # Clamp to valid range
    adjusted = max(0.1, min(1.0, adjusted))

    return round(adjusted, 3)
