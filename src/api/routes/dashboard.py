# =============================================================
# src/api/routes/dashboard.py
#
# Dashboard API endpoints for V3 self-calibration metrics
#
# Phase 5: calibration-profiles, calibration-summary, trigger-calibration
# Phase 6: model-improvements, improvement-history, trigger-evolution
# =============================================================

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from fastapi import APIRouter
from loguru import logger
from sqlalchemy import select, func, and_

from src.db.session import AsyncSessionFactory
from src.db.v3_models import (
    PredictionRecord,
    PredictionOutcome,
    PredictionAttribution,
    MarketEvent,
    CalibrationProfile,
    ModelImprovementLog,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── OVERALL METRICS ────────────────────────────────────────────────────────────

@router.get("/metrics")
async def get_overall_metrics() -> Dict[str, Any]:
    """Get overall system metrics."""
    async with AsyncSessionFactory() as db:
        total_result = await db.execute(
            select(func.count(PredictionRecord.id))
        )
        total = total_result.scalar() or 0
        
        evaluated_result = await db.execute(
            select(func.count(PredictionRecord.id))
            .where(PredictionRecord.evaluation_status == 'EVALUATED')
        )
        evaluated = evaluated_result.scalar() or 0
        
        correct_result = await db.execute(
            select(func.sum(PredictionOutcome.is_direction_correct))
        )
        correct = correct_result.scalar() or 0
        
        accuracy = (correct / evaluated * 100) if evaluated > 0 else 0
        
        avg_confidence_result = await db.execute(
            select(func.avg(PredictionRecord.confidence_score))
            .where(PredictionRecord.evaluation_status == 'EVALUATED')
        )
        avg_confidence = avg_confidence_result.scalar() or 0
        
        attributions_result = await db.execute(
            select(func.count(PredictionAttribution.id))
        )
        total_attributions = attributions_result.scalar() or 0
        
        # Phase 5
        calibration_result = await db.execute(
            select(func.count(CalibrationProfile.id))
            .where(CalibrationProfile.active == True)
        )
        active_calibrations = calibration_result.scalar() or 0
        
        # Phase 6
        improvements_result = await db.execute(
            select(func.count(ModelImprovementLog.id))
            .where(ModelImprovementLog.status == 'active')
        )
        active_improvements = improvements_result.scalar() or 0
        
        return {
            "total_predictions": total,
            "evaluated_predictions": evaluated,
            "correct_predictions": int(correct),
            "overall_accuracy_pct": round(accuracy, 1),
            "average_confidence": round(avg_confidence, 2),
            "total_attributions": total_attributions,
            "active_calibrations": active_calibrations,
            "active_improvements": active_improvements,
        }


# ── ACCURACY BY SECTOR ─────────────────────────────────────────────────────────

@router.get("/accuracy-by-sector")
async def get_accuracy_by_sector() -> List[Dict[str, Any]]:
    """Get accuracy metrics grouped by sector."""
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(
                PredictionRecord.sector,
                func.count(PredictionRecord.id).label('total'),
                func.sum(PredictionOutcome.is_direction_correct).label('correct'),
            )
            .join(PredictionOutcome, PredictionRecord.id == PredictionOutcome.prediction_id)
            .where(PredictionRecord.evaluation_status == 'EVALUATED')
            .group_by(PredictionRecord.sector)
            .order_by(func.sum(PredictionOutcome.is_direction_correct).desc())
        )
        
        sectors = []
        for row in result:
            sector = row.sector or 'Unknown'
            total = row.total or 0
            correct = int(row.correct or 0)
            accuracy = (correct / total * 100) if total > 0 else 0
            
            sectors.append({
                'sector': sector,
                'total': total,
                'correct': correct,
                'accuracy_pct': round(accuracy, 1),
            })
        
        return sectors


# ── ACCURACY BY CONFIDENCE BUCKET ──────────────────────────────────────────────

@router.get("/confidence-calibration")
async def get_confidence_calibration() -> List[Dict[str, Any]]:
    """Get accuracy vs confidence buckets to show calibration."""
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(
                PredictionRecord.confidence_score,
                PredictionOutcome.is_direction_correct,
            )
            .join(PredictionOutcome, PredictionRecord.id == PredictionOutcome.prediction_id)
            .where(PredictionRecord.evaluation_status == 'EVALUATED')
        )
    
    buckets = {
        '0.5-0.6': {'total': 0, 'correct': 0},
        '0.6-0.7': {'total': 0, 'correct': 0},
        '0.7-0.8': {'total': 0, 'correct': 0},
        '0.8-0.9': {'total': 0, 'correct': 0},
        '0.9-1.0': {'total': 0, 'correct': 0},
    }
    
    for row in result:
        conf = row.confidence_score
        correct = row.is_direction_correct
        
        if 0.5 <= conf < 0.6:
            bucket = '0.5-0.6'
        elif 0.6 <= conf < 0.7:
            bucket = '0.6-0.7'
        elif 0.7 <= conf < 0.8:
            bucket = '0.7-0.8'
        elif 0.8 <= conf < 0.9:
            bucket = '0.8-0.9'
        else:
            bucket = '0.9-1.0'
        
        buckets[bucket]['total'] += 1
        buckets[bucket]['correct'] += correct
    
    calibration = []
    for bucket, data in buckets.items():
        total = data['total']
        correct = data['correct']
        accuracy = (correct / total * 100) if total > 0 else 0
        
        calibration.append({
            'confidence_bucket': bucket,
            'total': total,
            'correct': correct,
            'accuracy_pct': round(accuracy, 1),
        })
    
    return calibration


# ── RECENT PREDICTIONS ─────────────────────────────────────────────────────────

@router.get("/recent-predictions")
async def get_recent_predictions(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent predictions with outcomes and attributions."""
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(
                PredictionRecord,
                PredictionOutcome,
            )
            .outerjoin(PredictionOutcome, PredictionRecord.id == PredictionOutcome.prediction_id)
            .where(PredictionRecord.evaluation_status == 'EVALUATED')
            .order_by(PredictionRecord.prediction_timestamp.desc())
            .limit(limit)
        )
        
        predictions = []
        for row in result:
            pred = row[0]
            outcome = row[1]
            
            attr_result = await db.execute(
                select(func.count(PredictionAttribution.id))
                .where(PredictionAttribution.prediction_id == pred.id)
            )
            attribution_count = attr_result.scalar() or 0
            
            predictions.append({
                'ticker': pred.ticker,
                'sector': pred.sector,
                'predicted_direction': pred.predicted_direction,
                'confidence': pred.confidence_score,
                'actual_return_pct': round(outcome.actual_return_pct, 2) if outcome else None,
                'is_correct': bool(outcome.is_direction_correct) if outcome else None,
                'accuracy_score': outcome.prediction_accuracy_score if outcome else None,
                'prediction_timestamp': pred.prediction_timestamp.isoformat(),
                'evaluation_timestamp': outcome.evaluation_timestamp.isoformat() if outcome else None,
                'attribution_count': attribution_count,
                'prompt_version': pred.prompt_version,
            })
    
    return predictions


# ── TOP ATTRIBUTIONS ───────────────────────────────────────────────────────────

@router.get("/top-attributions")
async def get_top_attributions(limit: int = 15) -> List[Dict[str, Any]]:
    """Get highest-scored attributions."""
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(
                PredictionRecord.ticker,
                PredictionAttribution.attribution_score,
                PredictionAttribution.explanation,
                MarketEvent.event_type,
                MarketEvent.title,
                MarketEvent.sentiment_score,
                MarketEvent.event_timestamp,
            )
            .join(PredictionRecord, PredictionAttribution.prediction_id == PredictionRecord.id)
            .join(MarketEvent, PredictionAttribution.event_id == MarketEvent.id)
            .order_by(PredictionAttribution.attribution_score.desc())
            .limit(limit)
        )
    
    attributions = []
    for row in result:
        explanation = row.explanation or ''
        attr_type = 'NEUTRAL'
        if explanation.startswith('[SUPPORTING]'):
            attr_type = 'SUPPORTING'
        elif explanation.startswith('[CONTRADICTING]'):
            attr_type = 'CONTRADICTING'
        
        attributions.append({
            'ticker': row.ticker,
            'score': round(row.attribution_score, 2),
            'type': attr_type,
            'event_type': row.event_type,
            'event_title': row.title,
            'event_sentiment': row.sentiment_score,
            'event_timestamp': row.event_timestamp.isoformat(),
            'explanation': explanation,
        })
    
    return attributions


# ── PREDICTION TIMELINE ────────────────────────────────────────────────────────

@router.get("/timeline")
async def get_prediction_timeline(days: int = 30) -> Dict[str, Any]:
    """Get daily prediction counts and accuracy over time."""
    async with AsyncSessionFactory() as db:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        result = await db.execute(
            select(
                func.date(PredictionRecord.prediction_timestamp).label('date'),
                func.count(PredictionRecord.id).label('total'),
                func.sum(PredictionOutcome.is_direction_correct).label('correct'),
            )
            .outerjoin(PredictionOutcome, PredictionRecord.id == PredictionOutcome.prediction_id)
            .where(PredictionRecord.prediction_timestamp >= start_date)
            .group_by(func.date(PredictionRecord.prediction_timestamp))
            .order_by('date')
        )
    
    timeline = []
    for row in result:
        total = row.total or 0
        correct = int(row.correct or 0)
        accuracy = (correct / total * 100) if total > 0 else 0
        
        timeline.append({
            'date': row.date.isoformat(),
            'total': total,
            'correct': correct,
            'accuracy_pct': round(accuracy, 1),
        })
    
    return {
        'days': days,
        'timeline': timeline,
    }


# =============================================================
# V3 PHASE 5: CALIBRATION PROFILE ENDPOINTS
# =============================================================

@router.get("/calibration-profiles")
async def get_calibration_profiles() -> List[Dict[str, Any]]:
    """Get all active calibration profiles."""
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(CalibrationProfile)
            .where(CalibrationProfile.active == True)
            .order_by(CalibrationProfile.bias_magnitude.desc())
        )
        
        profiles = []
        for p in result.scalars().all():
            profiles.append({
                'id': p.id,
                'sector': p.sector,
                'asset_class': p.asset_class,
                'bias_type': p.bias_type,
                'bias_magnitude': round(p.bias_magnitude, 3),
                'correction_factor': round(p.correction_factor, 3),
                'sample_size': p.sample_size,
                'detected_at': p.detected_at.isoformat(),
                'confidence_interval': p.confidence_interval,
                'scope': (
                    f"Sector: {p.sector}" if p.sector
                    else f"Class: {p.asset_class}" if p.asset_class
                    else "Global"
                ),
            })
        
        return profiles


@router.get("/calibration-summary")
async def get_calibration_summary() -> Dict[str, Any]:
    """Get a high-level summary of the calibration system status."""
    async with AsyncSessionFactory() as db:
        active_result = await db.execute(
            select(func.count(CalibrationProfile.id))
            .where(CalibrationProfile.active == True)
        )
        active_count = active_result.scalar() or 0
        
        total_result = await db.execute(
            select(func.count(CalibrationProfile.id))
        )
        total_count = total_result.scalar() or 0
        
        bias_result = await db.execute(
            select(
                CalibrationProfile.bias_type,
                func.count(CalibrationProfile.id).label('count'),
            )
            .where(CalibrationProfile.active == True)
            .group_by(CalibrationProfile.bias_type)
        )
        bias_distribution = {row.bias_type: row.count for row in bias_result}
        
        latest_result = await db.execute(
            select(func.max(CalibrationProfile.detected_at))
        )
        latest_run = latest_result.scalar()
        
        avg_correction_result = await db.execute(
            select(func.avg(CalibrationProfile.correction_factor))
            .where(CalibrationProfile.active == True)
        )
        avg_correction = avg_correction_result.scalar()
        
        return {
            'active_profiles': active_count,
            'total_profiles_ever': total_count,
            'bias_distribution': bias_distribution,
            'last_calibration_run': latest_run.isoformat() if latest_run else None,
            'avg_correction_factor': round(avg_correction, 3) if avg_correction else None,
            'system_status': 'calibrated' if active_count > 0 else 'uncalibrated',
        }


@router.post("/trigger-calibration")
async def trigger_calibration() -> Dict[str, Any]:
    """Manually trigger a calibration run."""
    try:
        from src.engine.calibration_engine import run_calibration_engine
        result = await run_calibration_engine()
        return result
    except Exception as e:
        logger.error(f"Manual calibration trigger failed: {e}")
        return {'status': 'error', 'error': str(e)}


# =============================================================
# V3 PHASE 6: MODEL IMPROVEMENT ENDPOINTS
# =============================================================

@router.get("/model-improvements")
async def get_model_improvements() -> List[Dict[str, Any]]:
    """
    Get all model improvement patches with their current status.
    Shows the full lifecycle: proposed → testing → active → retired.
    """
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(ModelImprovementLog)
            .order_by(ModelImprovementLog.created_at.desc())
            .limit(50)
        )
        
        improvements = []
        for patch in result.scalars().all():
            config = patch.new_config or {}
            improvements.append({
                'id': patch.id,
                'improvement_type': patch.improvement_type,
                'status': patch.status,
                'detected_issue': patch.detected_issue,
                'instruction': config.get('instruction', ''),
                'sector': config.get('sector'),
                'expected_improvement': patch.expected_improvement,
                'validation_metrics': patch.validation_metrics,
                'created_at': patch.created_at.isoformat(),
                'activated_at': patch.activated_at.isoformat() if patch.activated_at else None,
            })
        
        return improvements


@router.get("/improvement-summary")
async def get_improvement_summary() -> Dict[str, Any]:
    """
    Get high-level summary of the prompt evolution system.
    """
    async with AsyncSessionFactory() as db:
        # Count by status
        status_result = await db.execute(
            select(
                ModelImprovementLog.status,
                func.count(ModelImprovementLog.id).label('count'),
            )
            .group_by(ModelImprovementLog.status)
        )
        status_counts = {row.status: row.count for row in status_result}
        
        # Count by type (active only)
        type_result = await db.execute(
            select(
                ModelImprovementLog.improvement_type,
                func.count(ModelImprovementLog.id).label('count'),
            )
            .where(ModelImprovementLog.status == 'active')
            .group_by(ModelImprovementLog.improvement_type)
        )
        active_by_type = {row.improvement_type: row.count for row in type_result}
        
        # Latest evolution run
        latest_result = await db.execute(
            select(func.max(ModelImprovementLog.created_at))
        )
        latest_run = latest_result.scalar()
        
        # Current prompt version
        active_count = status_counts.get('active', 0)
        prompt_version = f"v1.0.0+{active_count}patches" if active_count > 0 else "v1.0.0"
        
        return {
            'status_counts': status_counts,
            'active_by_type': active_by_type,
            'total_patches_ever': sum(status_counts.values()),
            'current_prompt_version': prompt_version,
            'last_evolution_run': latest_run.isoformat() if latest_run else None,
            'system_status': 'evolving' if active_count > 0 else 'baseline',
        }


@router.post("/trigger-evolution")
async def trigger_evolution() -> Dict[str, Any]:
    """
    Manually trigger a prompt evolution run.
    Useful for testing or after manual calibration.
    """
    try:
        from src.engine.prompt_evolver import run_prompt_evolver
        result = await run_prompt_evolver()
        return result
    except Exception as e:
        logger.error(f"Manual evolution trigger failed: {e}")
        return {'status': 'error', 'error': str(e)}
