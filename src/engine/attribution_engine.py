# =============================================================
# src/engine/attribution_engine.py
#
# Links market events to prediction outcomes to explain
# why predictions succeeded or failed.
#
# WORKFLOW:
# 1. After prediction is evaluated
# 2. Find relevant events (ticker, sector, timeframe)
# 3. Score event impact on outcome
# 4. Store attribution records
#
# ATTRIBUTION SCORING:
# - Temporal proximity: Events closer to eval_date = higher score
# - Sentiment alignment: Event sentiment matches outcome direction
# - Event importance: EARNINGS > LEADERSHIP_CHANGE > GENERAL_NEWS
# =============================================================

from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from uuid import uuid4

from loguru import logger
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.v3_models import (
    PredictionRecord,
    PredictionOutcome,
    MarketEvent,
    PredictionAttribution,
)
from src.db.session import AsyncSessionFactory


# ── EVENT TYPE IMPORTANCE WEIGHTS ──────────────────────────────────────────────

EVENT_IMPORTANCE = {
    'EARNINGS': 1.0,              # Most important
    'FED_ANNOUNCEMENT': 0.9,
    'MERGER_ACQUISITION': 0.85,
    'LEADERSHIP_CHANGE': 0.7,
    'LEGAL_REGULATORY': 0.65,
    'PRODUCT_LAUNCH': 0.6,
    'GENERAL_NEWS': 0.3,          # Least important
}


# ── TEMPORAL PROXIMITY SCORING ─────────────────────────────────────────────────

def _calculate_temporal_score(
    event_time: datetime,
    prediction_time: datetime,
    evaluation_time: datetime,
) -> float:
    """
    Score based on how close the event is to the evaluation date.
    
    Events closer to evaluation have more impact.
    Events before prediction are less relevant.
    
    Returns: 0.0 to 1.0
    """
    # Events before prediction get lower score
    if event_time < prediction_time:
        days_before = (prediction_time - event_time).days
        # Decay: 1.0 at prediction_time, 0.5 at -7 days, 0.0 at -30 days
        if days_before > 30:
            return 0.0
        return max(0.0, 1.0 - (days_before / 30.0)) * 0.5
    
    # Events after prediction get higher score
    # Peak at evaluation time
    days_after = (event_time - prediction_time).days
    total_days = (evaluation_time - prediction_time).days
    
    if total_days == 0:
        return 1.0
    
    # Linear decay from evaluation time
    position = days_after / total_days
    
    # Events right before evaluation = highest score
    if position > 0.8:
        return 1.0
    elif position > 0.5:
        return 0.8
    else:
        return 0.5


# ── SENTIMENT ALIGNMENT SCORING ────────────────────────────────────────────────

def _calculate_sentiment_alignment(
    event_sentiment: float,
    prediction_direction: str,
    actual_direction: str,
    is_correct: bool,
) -> Tuple[float, str]:
    """
    Score how event sentiment aligns with prediction outcome.
    
    Returns: (score, attribution_type)
    - score: 0.0 to 1.0
    - attribution_type: 'SUPPORTING' | 'CONTRADICTING' | 'NEUTRAL'
    """
    # Determine if event sentiment matches outcome
    # event_sentiment: -1.0 (negative) to +1.0 (positive)
    
    # Actual market movement
    actual_positive = actual_direction in ['buy', 'hold']
    
    # Event was positive
    event_positive = event_sentiment > 0.1
    event_negative = event_sentiment < -0.1
    
    if is_correct:
        # Prediction was correct
        # If event sentiment matches actual direction → SUPPORTING
        if actual_positive and event_positive:
            return abs(event_sentiment), 'SUPPORTING'
        elif not actual_positive and event_negative:
            return abs(event_sentiment), 'SUPPORTING'
        else:
            return 0.3, 'NEUTRAL'
    
    else:
        # Prediction was wrong
        # If event sentiment contradicts prediction → CONTRADICTING
        predicted_positive = prediction_direction in ['buy', 'hold']
        
        if predicted_positive and event_negative:
            return abs(event_sentiment), 'CONTRADICTING'
        elif not predicted_positive and event_positive:
            return abs(event_sentiment), 'CONTRADICTING'
        else:
            return 0.3, 'NEUTRAL'


# ── FIND RELEVANT EVENTS ───────────────────────────────────────────────────────

async def _find_relevant_events(
    prediction: PredictionRecord,
    evaluation_time: datetime,
    db: AsyncSession,
) -> List[MarketEvent]:
    """
    Find market events relevant to this prediction.
    
    Criteria:
    - Matches ticker or sector
    - Occurred within ±7 days of evaluation
    - Or major market events (Fed, etc.)
    """
    ticker = prediction.ticker
    sector = prediction.sector
    
    # Time window: prediction time to evaluation time + 1 week
    start_time = prediction.prediction_timestamp - timedelta(days=7)
    end_time = evaluation_time + timedelta(days=1)
    
    # Query 1: Events mentioning this ticker
    ticker_query = select(MarketEvent).where(
        and_(
            MarketEvent.event_timestamp >= start_time,
            MarketEvent.event_timestamp <= end_time,
            MarketEvent.affected_tickers.contains(ticker),
        )
    )
    
    # Query 2: Major market events (Fed, etc.)
    major_query = select(MarketEvent).where(
        and_(
            MarketEvent.event_timestamp >= start_time,
            MarketEvent.event_timestamp <= end_time,
            MarketEvent.event_type.in_(['FED_ANNOUNCEMENT', 'EARNINGS']),
        )
    )
    
    # Query 3: Sector events (if sector available)
    sector_events = []
    if sector:
        sector_query = select(MarketEvent).where(
            and_(
                MarketEvent.event_timestamp >= start_time,
                MarketEvent.event_timestamp <= end_time,
                MarketEvent.affected_sectors.contains(sector),
            )
        )
        result = await db.execute(sector_query)
        sector_events = list(result.scalars().all())
    
    # Execute queries
    ticker_result = await db.execute(ticker_query)
    ticker_events = list(ticker_result.scalars().all())
    
    major_result = await db.execute(major_query)
    major_events = list(major_result.scalars().all())
    
    # Combine and deduplicate
    all_events = {e.id: e for e in ticker_events + major_events + sector_events}
    
    logger.info(
        f"Found {len(all_events)} relevant events for {ticker} "
        f"({len(ticker_events)} ticker, {len(major_events)} major, {len(sector_events)} sector)"
    )
    
    return list(all_events.values())


# ── CREATE ATTRIBUTION RECORD ──────────────────────────────────────────────────

async def _create_attribution(
    prediction_id: str,
    outcome_id: str,
    event: MarketEvent,
    attribution_score: float,
    attribution_type: str,
    reasoning: str,
    db: AsyncSession,
) -> PredictionAttribution:
    """
    Create a PredictionAttribution record linking event to prediction.
    """
    # Prepend attribution type to explanation
    explanation = f"[{attribution_type}] {reasoning}"
    
    attribution = PredictionAttribution(
        prediction_id=prediction_id,
        outcome_id=outcome_id,
        event_id=event.id,
        attribution_score=attribution_score,
        explanation=explanation,
    )
    
    db.add(attribution)
    await db.commit()
    await db.refresh(attribution)
    
    return attribution


# ── ANALYZE SINGLE PREDICTION ──────────────────────────────────────────────────

async def analyze_prediction_attribution(
    prediction_id: str,
    db: AsyncSession,
) -> int:
    """
    Analyze a single evaluated prediction and create attribution records.
    
    Returns: Number of attribution records created
    """
    # Fetch prediction and outcome
    pred_result = await db.execute(
        select(PredictionRecord).where(PredictionRecord.id == prediction_id)
    )
    prediction = pred_result.scalar_one_or_none()
    
    if not prediction:
        logger.warning(f"Prediction {prediction_id} not found")
        return 0
    
    if prediction.evaluation_status != 'EVALUATED':
        logger.info(f"Prediction {prediction_id} not yet evaluated, skipping attribution")
        return 0
    
    # Fetch outcome
    outcome_result = await db.execute(
        select(PredictionOutcome).where(PredictionOutcome.prediction_id == prediction_id)
    )
    outcome = outcome_result.scalar_one_or_none()
    
    if not outcome:
        logger.warning(f"No outcome found for prediction {prediction_id}")
        return 0
    
    # Find relevant events
    events = await _find_relevant_events(
        prediction,
        outcome.evaluation_timestamp,
        db,
    )
    
    if not events:
        logger.info(f"No relevant events found for {prediction.ticker}")
        return 0
    
    # Score each event
    attributions_created = 0
    
    for event in events:
        # Calculate temporal score
        temporal_score = _calculate_temporal_score(
            event.event_timestamp,
            prediction.prediction_timestamp,
            outcome.evaluation_timestamp,
        )
        
        # Calculate sentiment alignment
        actual_direction = 'buy' if outcome.actual_return_pct > 0 else 'avoid'
        sentiment_score, attribution_type = _calculate_sentiment_alignment(
            event.sentiment_score or 0.0,
            prediction.predicted_direction,
            actual_direction,
            outcome.is_direction_correct == 1,
        )
        
        # Get event importance weight
        importance = EVENT_IMPORTANCE.get(event.event_type, 0.3)
        
        # Combined attribution score
        attribution_score = (
            temporal_score * 0.4 +
            sentiment_score * 0.4 +
            importance * 0.2
        )
        
        # Only create attribution if score is meaningful (> 0.3)
        if attribution_score < 0.3:
            continue
        
        # Generate reasoning
        reasoning = (
            f"Event '{event.title[:100]}' occurred {(event.event_timestamp - prediction.prediction_timestamp).days}d "
            f"after prediction. Type: {event.event_type}, Sentiment: {event.sentiment_score:.2f}. "
            f"{'Supported' if attribution_type == 'SUPPORTING' else 'Contradicted' if attribution_type == 'CONTRADICTING' else 'Neutral to'} "
            f"the {'correct' if outcome.is_direction_correct else 'incorrect'} prediction."
        )
        
        # Create attribution record
        await _create_attribution(
            prediction.id,
            outcome.id,  # Add outcome_id
            event,
            round(attribution_score, 3),
            attribution_type,
            reasoning,
            db,
        )
        
        attributions_created += 1
        
        logger.info(
            f"Created attribution: {prediction.ticker} ← {event.event_type} "
            f"(score={attribution_score:.2f}, type={attribution_type})"
        )
    
    return attributions_created


# ── PUBLIC: RUN ATTRIBUTION ANALYSIS ───────────────────────────────────────────

async def run_attribution_analysis() -> dict:
    """
    Run attribution analysis on all evaluated predictions without attributions.
    
    Returns: Statistics dictionary
    """
    logger.info("Starting attribution analysis")
    
    async with AsyncSessionFactory() as db:
        # Find evaluated predictions without attributions
        result = await db.execute(
            select(PredictionRecord).where(
                PredictionRecord.evaluation_status == 'EVALUATED'
            )
        )
        evaluated_predictions = list(result.scalars().all())
        
        logger.info(f"Found {len(evaluated_predictions)} evaluated predictions")
        
        total_attributions = 0
        predictions_analyzed = 0
        
        for prediction in evaluated_predictions:
            # Check if already has attributions
            existing = await db.execute(
                select(PredictionAttribution).where(
                    PredictionAttribution.prediction_id == prediction.id
                ).limit(1)
            )
            
            if existing.scalar_one_or_none():
                logger.debug(f"Prediction {prediction.ticker} already has attributions, skipping")
                continue
            
            # Analyze this prediction
            count = await analyze_prediction_attribution(prediction.id, db)
            total_attributions += count
            predictions_analyzed += 1
        
        logger.info(
            f"Attribution analysis complete: {predictions_analyzed} predictions analyzed, "
            f"{total_attributions} attributions created"
        )
        
        return {
            'predictions_analyzed': predictions_analyzed,
            'attributions_created': total_attributions,
            'avg_attributions_per_prediction': (
                total_attributions / predictions_analyzed if predictions_analyzed > 0 else 0
            ),
        }
