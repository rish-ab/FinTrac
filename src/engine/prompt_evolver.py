# =============================================================
# src/engine/prompt_evolver.py
#
# FinTrac V3 — Phase 6: Prompt Evolution Engine
#
# WHAT THIS DOES:
# Analyzes prediction outcomes and calibration profiles to identify
# specific, actionable failure patterns. Generates targeted prompt
# patches — additional instructions injected into the system prompt
# to fix blind spots. Manages the full lifecycle of these patches:
#   proposed → testing → active → retired
#
# WHY PROMPT PATCHES INSTEAD OF REWRITING THE WHOLE PROMPT?
# Full prompt rewrites are fragile. Changing one sentence can break
# JSON output compliance or alter the AI's personality. Instead, we
# append surgical patches: "When analyzing {sector}, also consider
# {specific factor}." These are additive and independently testable.
#
# IMPROVEMENT TYPES:
#   sector_guidance    — Sector-specific analysis instructions
#   confidence_anchor  — Explicit confidence ceiling for known weak areas  
#   risk_emphasis      — Additional risk factors to check
#   data_gap_warning   — Known data blind spots to flag
#   direction_guard    — Counter-bias instructions when direction bias exists
#
# LIFECYCLE:
#   1. Engine detects pattern → writes ModelImprovementLog (status=proposed)
#   2. Next run: if proposed patch exists for 24h+ → promote to testing
#   3. After N predictions made under testing → compare accuracy → active or retired
#   4. When a new patch supersedes an old one → old becomes retired
#
# VALIDATION:
#   A patch is promoted from testing → active only if predictions made
#   while it was in testing show improvement (or at least no regression).
#   If accuracy drops, the patch is retired immediately.
#
# CALLED BY: scheduler.py (runs after calibration engine, every 7 days)
# =============================================================

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.v3_models import (
    PredictionRecord,
    PredictionOutcome,
    CalibrationProfile,
    ModelImprovementLog,
)
from src.db.session import AsyncSessionFactory


# ── CONFIGURATION ──────────────────────────────────────────────────────────────

MIN_PREDICTIONS_FOR_VALIDATION = 5   # Minimum predictions under a testing patch before promoting
TESTING_PERIOD_HOURS = 24            # Minimum hours before proposed → testing
ACCURACY_REGRESSION_THRESHOLD = 5.0  # If accuracy drops by 5%+ under testing, retire the patch


# ── PATTERN DETECTORS ──────────────────────────────────────────────────────────
# Each detector returns a list of (improvement_type, detected_issue, new_config)
# tuples. new_config is a JSON dict with the patch content.

async def _detect_sector_weaknesses(db: AsyncSession) -> List[Tuple[str, str, dict]]:
    """
    Find sectors where accuracy is significantly below global average.
    Generate sector-specific guidance patches.
    """
    improvements = []
    
    # Get global accuracy
    global_result = await db.execute(
        select(
            func.count(PredictionOutcome.id).label('total'),
            func.sum(PredictionOutcome.is_direction_correct).label('correct'),
        )
    )
    global_row = global_result.one()
    global_total = global_row.total or 0
    global_correct = int(global_row.correct or 0)
    global_accuracy = (global_correct / global_total * 100) if global_total > 0 else 50
    
    # Get per-sector accuracy
    sector_result = await db.execute(
        select(
            PredictionRecord.sector,
            func.count(PredictionRecord.id).label('total'),
            func.sum(PredictionOutcome.is_direction_correct).label('correct'),
            func.avg(PredictionRecord.confidence_score).label('avg_confidence'),
        )
        .join(PredictionOutcome, PredictionRecord.id == PredictionOutcome.prediction_id)
        .where(PredictionRecord.evaluation_status == 'EVALUATED')
        .group_by(PredictionRecord.sector)
        .having(func.count(PredictionRecord.id) >= 5)
    )
    
    for row in sector_result:
        sector = row.sector or 'Unknown'
        total = row.total
        correct = int(row.correct or 0)
        accuracy = (correct / total * 100) if total > 0 else 0
        avg_conf = row.avg_confidence or 0
        
        # Sector is 15%+ below global accuracy
        if accuracy < (global_accuracy - 15):
            improvements.append((
                'sector_guidance',
                (
                    f"Sector '{sector}' has {accuracy:.0f}% accuracy vs "
                    f"{global_accuracy:.0f}% global ({total} predictions). "
                    f"Average confidence {avg_conf:.0%} is not justified by results."
                ),
                {
                    'type': 'sector_guidance',
                    'sector': sector,
                    'instruction': (
                        f"SECTOR ALERT — {sector}: Your past predictions in this sector "
                        f"have been {accuracy:.0f}% accurate (below the {global_accuracy:.0f}% "
                        f"global average). Exercise extra caution. Specifically:\n"
                        f"  - Lower your confidence by at least 15% for {sector} assets\n"
                        f"  - Pay closer attention to sector-specific risk factors\n"
                        f"  - If recommending BUY, require stronger supporting evidence\n"
                        f"  - Explicitly flag at least 2 sector-specific risks"
                    ),
                    'accuracy_at_detection': accuracy,
                    'global_accuracy_at_detection': global_accuracy,
                    'sample_size': total,
                }
            ))
    
    return improvements


async def _detect_confidence_miscalibration(db: AsyncSession) -> List[Tuple[str, str, dict]]:
    """
    Find specific confidence ranges where accuracy is worst.
    Generate confidence anchoring patches.
    """
    improvements = []
    
    # Get predictions grouped by confidence bucket
    result = await db.execute(
        select(
            PredictionRecord.confidence_score,
            PredictionOutcome.is_direction_correct,
        )
        .join(PredictionOutcome, PredictionRecord.id == PredictionOutcome.prediction_id)
        .where(PredictionRecord.evaluation_status == 'EVALUATED')
    )
    
    # Bucket into high-confidence (0.8+) and low-confidence (<0.6)
    high_conf = {'total': 0, 'correct': 0}
    low_conf = {'total': 0, 'correct': 0}
    
    for row in result:
        if row.confidence_score >= 0.8:
            high_conf['total'] += 1
            high_conf['correct'] += int(row.is_direction_correct or 0)
        elif row.confidence_score < 0.6:
            low_conf['total'] += 1
            low_conf['correct'] += int(row.is_direction_correct or 0)
    
    # High confidence predictions should be MORE accurate, not less
    if high_conf['total'] >= 5:
        high_accuracy = (high_conf['correct'] / high_conf['total'] * 100)
        
        if high_accuracy < 55:
            improvements.append((
                'confidence_anchor',
                (
                    f"High-confidence predictions (0.8+) are only {high_accuracy:.0f}% "
                    f"accurate across {high_conf['total']} predictions. The model assigns "
                    f"high confidence without justification."
                ),
                {
                    'type': 'confidence_anchor',
                    'instruction': (
                        "CONFIDENCE CALIBRATION RULE: Your high-confidence predictions "
                        "(0.8+) have historically been unreliable. Apply these rules:\n"
                        "  - Do NOT assign confidence above 0.75 unless ALL of these are true:\n"
                        "    a) Strong fundamental metrics (low P/E, positive cash flow)\n"
                        "    b) Positive momentum (price above 200-day SMA)\n"
                        "    c) No major risk flags in the sector\n"
                        "  - Default confidence range should be 0.50-0.70\n"
                        "  - Confidence above 0.85 requires exceptional circumstances"
                    ),
                    'high_conf_accuracy': high_accuracy,
                    'high_conf_total': high_conf['total'],
                }
            ))
    
    return improvements


async def _detect_direction_patterns(db: AsyncSession) -> List[Tuple[str, str, dict]]:
    """
    Detect if the AI always predicts the same direction regardless of data.
    Generate direction guard patches.
    """
    improvements = []
    
    result = await db.execute(
        select(
            PredictionRecord.predicted_direction,
            func.count(PredictionRecord.id).label('total'),
            func.sum(PredictionOutcome.is_direction_correct).label('correct'),
        )
        .join(PredictionOutcome, PredictionRecord.id == PredictionOutcome.prediction_id)
        .where(PredictionRecord.evaluation_status == 'EVALUATED')
        .group_by(PredictionRecord.predicted_direction)
    )
    
    direction_stats = {}
    grand_total = 0
    for row in result:
        direction = row.predicted_direction
        total = row.total
        correct = int(row.correct or 0)
        direction_stats[direction] = {
            'total': total,
            'correct': correct,
            'accuracy': (correct / total * 100) if total > 0 else 0,
        }
        grand_total += total
    
    if grand_total < 10:
        return improvements
    
    # Check for dominant direction
    for direction, stats in direction_stats.items():
        ratio = stats['total'] / grand_total
        
        if ratio > 0.70 and stats['accuracy'] < 55:
            opposite = 'AVOID' if direction in ('buy', 'long', 'bullish') else 'BUY'
            improvements.append((
                'direction_guard',
                (
                    f"Direction '{direction}' accounts for {ratio:.0%} of all predictions "
                    f"but is only {stats['accuracy']:.0f}% accurate. The model defaults "
                    f"to '{direction}' without sufficient differentiation."
                ),
                {
                    'type': 'direction_guard',
                    'dominant_direction': direction,
                    'instruction': (
                        f"DIRECTION BIAS CORRECTION: You have a strong tendency to predict "
                        f"'{direction.upper()}'. {ratio:.0%} of your past predictions were "
                        f"'{direction.upper()}' but only {stats['accuracy']:.0f}% were correct.\n"
                        f"  - Before defaulting to {direction.upper()}, explicitly consider "
                        f"the case for {opposite}\n"
                        f"  - List at least one reason why {opposite} might be correct\n"
                        f"  - If you cannot find strong evidence AGAINST {opposite}, "
                        f"assign {opposite} or HOLD instead"
                    ),
                    'direction_ratio': round(ratio, 2),
                    'direction_accuracy': round(stats['accuracy'], 1),
                }
            ))
    
    return improvements


async def _detect_risk_blind_spots(db: AsyncSession) -> List[Tuple[str, str, dict]]:
    """
    Find predictions that were wrong AND had high confidence — these are
    the blind spots where the AI was most dangerously wrong.
    Analyze common patterns in these failures.
    """
    improvements = []
    
    # Get high-confidence wrong predictions
    result = await db.execute(
        select(PredictionRecord, PredictionOutcome)
        .join(PredictionOutcome, PredictionRecord.id == PredictionOutcome.prediction_id)
        .where(
            and_(
                PredictionRecord.evaluation_status == 'EVALUATED',
                PredictionRecord.confidence_score >= 0.75,
                PredictionOutcome.is_direction_correct == False,
            )
        )
        .order_by(PredictionOutcome.absolute_error.desc())
        .limit(20)
    )
    
    failures = []
    sectors_in_failures = {}
    
    for row in result:
        pred = row[0]
        outcome = row[1]
        failures.append({
            'ticker': pred.ticker,
            'sector': pred.sector,
            'confidence': pred.confidence_score,
            'predicted': pred.predicted_direction,
            'actual_return': outcome.actual_return_pct,
            'error': outcome.absolute_error,
        })
        
        sector = pred.sector or 'Unknown'
        if sector not in sectors_in_failures:
            sectors_in_failures[sector] = 0
        sectors_in_failures[sector] += 1
    
    if len(failures) < 3:
        return improvements
    
    # Find sectors that appear disproportionately in high-confidence failures
    total_failures = len(failures)
    for sector, count in sectors_in_failures.items():
        if count >= 3 and (count / total_failures) > 0.3:
            avg_error = sum(
                f['error'] for f in failures if f['sector'] == sector
            ) / count
            
            improvements.append((
                'risk_emphasis',
                (
                    f"Sector '{sector}' appears in {count}/{total_failures} high-confidence "
                    f"failures (avg error: {avg_error:.1f}%). The model misses critical "
                    f"risk factors in this sector."
                ),
                {
                    'type': 'risk_emphasis',
                    'sector': sector,
                    'instruction': (
                        f"RISK BLIND SPOT — {sector}: You have repeatedly made high-confidence "
                        f"predictions in {sector} that were wrong (avg error: {avg_error:.1f}%). "
                        f"Before issuing any verdict for {sector} assets:\n"
                        f"  - Check for recent earnings surprises or guidance changes\n"
                        f"  - Evaluate if macro conditions (interest rates, regulation) "
                        f"specifically affect this sector\n"
                        f"  - Compare the asset's valuation metrics to sector median, not market median\n"
                        f"  - Flag ANY missing data as a risk — do not assume missing data is neutral"
                    ),
                    'failure_count': count,
                    'total_high_conf_failures': total_failures,
                    'avg_error': round(avg_error, 2),
                }
            ))
    
    return improvements


# ── LIFECYCLE MANAGEMENT ───────────────────────────────────────────────────────

async def _promote_proposed_to_testing(db: AsyncSession) -> int:
    """
    Move patches from 'proposed' to 'testing' if they have been
    proposed for at least TESTING_PERIOD_HOURS.
    
    Returns number promoted.
    """
    cutoff = datetime.utcnow() - timedelta(hours=TESTING_PERIOD_HOURS)
    
    result = await db.execute(
        select(ModelImprovementLog).where(
            and_(
                ModelImprovementLog.status == 'proposed',
                ModelImprovementLog.created_at <= cutoff,
            )
        )
    )
    
    promoted = 0
    for patch in result.scalars().all():
        patch.status = 'testing'
        promoted += 1
        logger.info(
            f"Promoted patch {patch.id[:8]}... ({patch.improvement_type}) "
            f"from proposed → testing"
        )
    
    if promoted > 0:
        await db.commit()
    
    return promoted


async def _validate_testing_patches(db: AsyncSession) -> Tuple[int, int]:
    """
    Check patches in 'testing' status. If enough predictions have been
    made while the patch was active, compare accuracy and decide:
      - Accuracy improved or held → promote to 'active'
      - Accuracy regressed → retire the patch
    
    Returns (promoted_count, retired_count).
    """
    result = await db.execute(
        select(ModelImprovementLog).where(
            ModelImprovementLog.status == 'testing'
        )
    )
    
    promoted = 0
    retired = 0
    
    for patch in result.scalars().all():
        # Count predictions made after this patch entered testing
        pred_result = await db.execute(
            select(
                func.count(PredictionRecord.id).label('total'),
                func.sum(PredictionOutcome.is_direction_correct).label('correct'),
            )
            .join(PredictionOutcome, PredictionRecord.id == PredictionOutcome.prediction_id)
            .where(
                and_(
                    PredictionRecord.evaluation_status == 'EVALUATED',
                    PredictionRecord.prediction_timestamp >= patch.created_at,
                )
            )
        )
        
        pred_row = pred_result.one()
        total = pred_row.total or 0
        correct = int(pred_row.correct or 0)
        
        if total < MIN_PREDICTIONS_FOR_VALIDATION:
            logger.debug(
                f"Patch {patch.id[:8]}... has {total} predictions "
                f"(need {MIN_PREDICTIONS_FOR_VALIDATION}), deferring validation"
            )
            continue
        
        post_accuracy = (correct / total * 100) if total > 0 else 0
        
        # Get pre-patch accuracy from the patch's detection context
        pre_accuracy = 50.0  # default
        if patch.new_config and 'accuracy_at_detection' in patch.new_config:
            pre_accuracy = patch.new_config['accuracy_at_detection']
        elif patch.new_config and 'global_accuracy_at_detection' in patch.new_config:
            pre_accuracy = patch.new_config['global_accuracy_at_detection']
        
        # Decision: did accuracy regress?
        regression = pre_accuracy - post_accuracy
        
        validation_metrics = {
            'pre_accuracy': round(pre_accuracy, 1),
            'post_accuracy': round(post_accuracy, 1),
            'predictions_evaluated': total,
            'regression': round(regression, 1),
            'validated_at': datetime.utcnow().isoformat(),
        }
        
        if regression > ACCURACY_REGRESSION_THRESHOLD:
            # Accuracy dropped — retire this patch
            patch.status = 'retired'
            patch.validation_metrics = validation_metrics
            retired += 1
            logger.warning(
                f"RETIRED patch {patch.id[:8]}... ({patch.improvement_type}): "
                f"accuracy regressed {pre_accuracy:.1f}% → {post_accuracy:.1f}%"
            )
        else:
            # Accuracy held or improved — promote to active
            patch.status = 'active'
            patch.activated_at = datetime.utcnow()
            patch.validation_metrics = validation_metrics
            promoted += 1
            logger.info(
                f"ACTIVATED patch {patch.id[:8]}... ({patch.improvement_type}): "
                f"accuracy {pre_accuracy:.1f}% → {post_accuracy:.1f}%"
            )
    
    if promoted + retired > 0:
        await db.commit()
    
    return promoted, retired


async def _retire_superseded_patches(db: AsyncSession) -> int:
    """
    If multiple active patches exist for the same improvement_type,
    keep only the most recent one and retire the rest.
    
    Returns number retired.
    """
    # Find active patches grouped by type
    result = await db.execute(
        select(ModelImprovementLog)
        .where(ModelImprovementLog.status == 'active')
        .order_by(
            ModelImprovementLog.improvement_type,
            ModelImprovementLog.activated_at.desc(),
        )
    )
    
    patches_by_type: Dict[str, List] = {}
    for patch in result.scalars().all():
        key = patch.improvement_type
        # For sector-specific patches, include sector in the key
        if patch.new_config and 'sector' in patch.new_config:
            key = f"{patch.improvement_type}:{patch.new_config['sector']}"
        
        if key not in patches_by_type:
            patches_by_type[key] = []
        patches_by_type[key].append(patch)
    
    retired = 0
    for key, patches in patches_by_type.items():
        if len(patches) > 1:
            # Keep the first (most recent), retire the rest
            for old_patch in patches[1:]:
                old_patch.status = 'retired'
                retired += 1
                logger.info(
                    f"Retired superseded patch {old_patch.id[:8]}... "
                    f"({key}), replaced by {patches[0].id[:8]}..."
                )
    
    if retired > 0:
        await db.commit()
    
    return retired


# ── DUPLICATE CHECK ────────────────────────────────────────────────────────────

async def _already_has_patch(
    db: AsyncSession,
    improvement_type: str,
    sector: Optional[str] = None,
) -> bool:
    """
    Check if an active or testing patch already exists for this type+sector.
    Avoids creating duplicate patches every run.
    """
    query = select(func.count(ModelImprovementLog.id)).where(
        and_(
            ModelImprovementLog.improvement_type == improvement_type,
            ModelImprovementLog.status.in_(['proposed', 'testing', 'active']),
        )
    )
    
    # For sector-specific patches, check the JSON config
    # This is a simplified check — matches on type only
    result = await db.execute(query)
    count = result.scalar() or 0
    
    return count > 0


# ── MAIN: RUN PROMPT EVOLUTION ────────────────────────────────────────────────

async def run_prompt_evolver() -> dict:
    """
    Main entry point. Detects failure patterns, generates prompt patches,
    and manages the improvement lifecycle.
    
    Called by scheduler.py after calibration engine (every 7 days).
    
    Returns statistics about the evolution run.
    """
    logger.info("═══ PROMPT EVOLVER: Starting evolution run ═══")
    
    async with AsyncSessionFactory() as db:
        # ── STEP 1: LIFECYCLE MANAGEMENT ───────────────────────
        # Process existing patches before generating new ones
        
        promoted_to_testing = await _promote_proposed_to_testing(db)
        promoted_to_active, retired_from_testing = await _validate_testing_patches(db)
        retired_superseded = await _retire_superseded_patches(db)
        
        logger.info(
            f"Lifecycle: {promoted_to_testing} proposed→testing, "
            f"{promoted_to_active} testing→active, "
            f"{retired_from_testing} testing→retired, "
            f"{retired_superseded} superseded→retired"
        )
        
        # ── STEP 2: DETECT NEW PATTERNS ────────────────────────
        # Run all pattern detectors
        
        all_improvements = []
        
        detectors = [
            ('sector_weaknesses', _detect_sector_weaknesses),
            ('confidence_miscalibration', _detect_confidence_miscalibration),
            ('direction_patterns', _detect_direction_patterns),
            ('risk_blind_spots', _detect_risk_blind_spots),
        ]
        
        for name, detector in detectors:
            try:
                found = await detector(db)
                all_improvements.extend(found)
                if found:
                    logger.info(f"Detector '{name}' found {len(found)} improvements")
            except Exception as e:
                logger.error(f"Detector '{name}' failed: {e}")
        
        # ── STEP 3: WRITE NEW PATCHES ─────────────────────────
        # Only write if no existing active/testing patch for this type
        
        patches_created = 0
        
        for improvement_type, detected_issue, new_config in all_improvements:
            # Check for duplicates
            sector = new_config.get('sector')
            has_existing = await _already_has_patch(db, improvement_type, sector)
            
            if has_existing:
                logger.debug(
                    f"Skipping duplicate patch: {improvement_type} "
                    f"(sector={sector})"
                )
                continue
            
            # Get current prompt config as old_config
            old_config = {
                'system_prompt_version': 'v1.0.0',
                'note': 'No sector-specific instructions existed before this patch',
            }
            
            patch = ModelImprovementLog(
                improvement_type=improvement_type,
                detected_issue=detected_issue,
                old_config=old_config,
                new_config=new_config,
                expected_improvement=(
                    f"Targeted guidance for {improvement_type} should improve "
                    f"accuracy in the identified weak area by reducing blind "
                    f"confidence and forcing explicit risk evaluation."
                ),
                validation_metrics=None,
                status='proposed',
            )
            
            db.add(patch)
            patches_created += 1
            
            logger.info(
                f"NEW PATCH proposed: {improvement_type} — "
                f"{detected_issue[:100]}..."
            )
        
        if patches_created > 0:
            await db.commit()
        
        # ── STEP 4: SUMMARY ───────────────────────────────────
        
        # Count current active patches
        active_result = await db.execute(
            select(func.count(ModelImprovementLog.id))
            .where(ModelImprovementLog.status == 'active')
        )
        active_count = active_result.scalar() or 0
        
        summary = {
            'status': 'completed',
            'patches_created': patches_created,
            'promoted_to_testing': promoted_to_testing,
            'promoted_to_active': promoted_to_active,
            'retired_from_testing': retired_from_testing,
            'retired_superseded': retired_superseded,
            'total_active_patches': active_count,
            'patterns_detected': len(all_improvements),
        }
        
        logger.info(
            f"═══ PROMPT EVOLVER COMPLETE: "
            f"{patches_created} new patches, "
            f"{active_count} total active ═══"
        )
        
        return summary


# ── PUBLIC: GET ACTIVE IMPROVEMENTS ───────────────────────────────────────────

async def get_active_improvements() -> List[dict]:
    """
    Retrieve all active prompt improvement patches.
    Used by advisor_agent.py to inject into the prompt at inference time.
    
    Returns list of dicts with improvement_type and instruction text.
    """
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(ModelImprovementLog)
            .where(ModelImprovementLog.status == 'active')
            .order_by(ModelImprovementLog.activated_at.desc())
        )
        
        improvements = []
        for patch in result.scalars().all():
            config = patch.new_config or {}
            instruction = config.get('instruction', '')
            
            if instruction:
                improvements.append({
                    'id': patch.id,
                    'type': patch.improvement_type,
                    'instruction': instruction,
                    'sector': config.get('sector'),
                    'activated_at': patch.activated_at.isoformat() if patch.activated_at else None,
                })
        
        return improvements


def format_improvements_for_prompt(improvements: List[dict]) -> str:
    """
    Format active improvement patches into a prompt block.
    Injected into the INVESTMENT_PROMPT after calibration context.
    
    Returns empty string if no active improvements.
    """
    if not improvements:
        return ""
    
    lines = [
        "=== LEARNED IMPROVEMENTS (from past performance analysis) ===",
        "The following rules were learned from analyzing your prediction history.",
        "Follow them strictly:\n",
    ]
    
    for i, imp in enumerate(improvements, 1):
        lines.append(f"Rule {i} [{imp['type'].upper()}]:")
        lines.append(imp['instruction'])
        lines.append("")  # blank line between rules
    
    return "\n".join(lines)


def get_active_prompt_version(improvements: List[dict]) -> str:
    """
    Generate a version string based on active improvements.
    Used to track which prompt version produced each prediction.
    
    Format: v1.0.0+{count}patches
    """
    if not improvements:
        return "v1.0.0"
    
    return f"v1.0.0+{len(improvements)}patches"
