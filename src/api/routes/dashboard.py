# =============================================================
# src/api/routes/dashboard.py
#
# Dashboard API endpoints for V3 self-calibration metrics
# Provides data for accuracy visualization
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
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── OVERALL METRICS ────────────────────────────────────────────────────────────

@router.get("/metrics")
async def get_overall_metrics() -> Dict[str, Any]:
    """
    Get overall system metrics.
    """
    async with AsyncSessionFactory() as db:
        # Total predictions
        total_result = await db.execute(
            select(func.count(PredictionRecord.id))
        )
        total = total_result.scalar() or 0
        
        # Evaluated predictions
        evaluated_result = await db.execute(
            select(func.count(PredictionRecord.id))
            .where(PredictionRecord.evaluation_status == 'EVALUATED')
        )
        evaluated = evaluated_result.scalar() or 0
        
        # Correct predictions
        correct_result = await db.execute(
            select(func.sum(PredictionOutcome.is_direction_correct))
        )
        correct = correct_result.scalar() or 0
        
        # Overall accuracy
        accuracy = (correct / evaluated * 100) if evaluated > 0 else 0
        
        # Average confidence
        avg_confidence_result = await db.execute(
            select(func.avg(PredictionRecord.confidence_score))
            .where(PredictionRecord.evaluation_status == 'EVALUATED')
        )
        avg_confidence = avg_confidence_result.scalar() or 0
        
        # Total attributions
        attributions_result = await db.execute(
            select(func.count(PredictionAttribution.id))
        )
        total_attributions = attributions_result.scalar() or 0
        
        return {
            "total_predictions": total,
            "evaluated_predictions": evaluated,
            "correct_predictions": int(correct),
            "overall_accuracy_pct": round(accuracy, 1),
            "average_confidence": round(avg_confidence, 2),
            "total_attributions": total_attributions,
        }


# ── ACCURACY BY SECTOR ─────────────────────────────────────────────────────────

@router.get("/accuracy-by-sector")
async def get_accuracy_by_sector() -> List[Dict[str, Any]]:
    """
    Get accuracy metrics grouped by sector.
    """
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
    """
    Get accuracy vs confidence buckets to show calibration.
    """
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(
                PredictionRecord.confidence_score,
                PredictionOutcome.is_direction_correct,
            )
            .join(PredictionOutcome, PredictionRecord.id == PredictionOutcome.prediction_id)
            .where(PredictionRecord.evaluation_status == 'EVALUATED')
        )
    
    # Bucket predictions by confidence
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
    
    # Convert to list
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
    """
    Get recent predictions with outcomes and attributions.
    """
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
            
            # Count attributions for this prediction
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
        })
    
    return predictions


# ── TOP ATTRIBUTIONS ───────────────────────────────────────────────────────────

@router.get("/top-attributions")
async def get_top_attributions(limit: int = 15) -> List[Dict[str, Any]]:
    """
    Get highest-scored attributions.
    """
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
        # Extract attribution type from explanation
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
    """
    Get daily prediction counts and accuracy over time.
    """
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
