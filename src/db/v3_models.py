# =============================================================
# src/db/v3_models.py
#
# FinTrac V3 Self-Calibration Models
# 
# WHAT THESE TABLES DO:
# V3 adds a feedback loop where the AI tracks its own predictions,
# compares them to reality, identifies systematic biases, and
# rewrites its analysis prompts to fix blind spots.
#
# INTEGRATION:
# These models extend the existing V2 Base class and follow the
# same UUID/relationship patterns. Import them alongside V2 models
# in your routes when V3 features are needed.
# =============================================================

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, JSON, String, Text, Index
)
from sqlalchemy.dialects.mysql import CHAR, BLOB
from sqlalchemy.orm import relationship

from src.db.models import Base, new_uuid


# =============================================================
# SECTION 1: PREDICTION TRACKING
# =============================================================

class PredictionRecord(Base):
    """
    Stores every AI prediction with full context.
    Created whenever the AI evaluates an asset and makes a forecast.
    
    WHY RECORD PREDICTIONS?
    Without this, we have no way to measure if the AI is accurate.
    V3 turns FinTrac into a self-improving system by tracking what
    it predicted vs what actually happened.
    """
    __tablename__ = "prediction_record"
    
    __table_args__ = (
        Index("ix_prediction_ticker_timestamp", "ticker", "prediction_timestamp"),
        Index("ix_prediction_sector_timestamp", "sector", "prediction_timestamp"),
    )
    
    id                   = Column(CHAR(36), primary_key=True, default=new_uuid)
    ticker               = Column(String(20), nullable=False)
    prediction_timestamp = Column(DateTime, nullable=False, index=True)
    prediction_horizon   = Column(String(20), nullable=False)  # 1d, 1w, 1m, 3m
    predicted_direction  = Column(String(10), nullable=False)  # up, down, neutral
    predicted_return_pct = Column(Float, nullable=True)
    confidence_score     = Column(Float, nullable=False)       # 0.0 to 1.0
    analysis_context     = Column(JSON, nullable=False)        # Full AI reasoning
    prompt_version       = Column(String(50), nullable=False)
    model_version        = Column(String(50), nullable=False)
    sector               = Column(String(100), nullable=True, index=True)
    asset_class          = Column(String(50), nullable=True, index=True)
    
    # Evaluation tracking
    evaluation_status    = Column(String(20), nullable=False, default='PENDING')  # PENDING, EVALUATED, FAILED
    evaluation_due_at    = Column(DateTime, nullable=True, index=True)  # When to evaluate this prediction
    
    created_at           = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    outcome      = relationship("PredictionOutcome", back_populates="prediction",
                                uselist=False, cascade="all, delete-orphan")
    attributions = relationship("PredictionAttribution", back_populates="prediction",
                                cascade="all, delete-orphan")


class PredictionOutcome(Base):
    """
    Evaluation results comparing prediction vs reality.
    Created by scheduled job when prediction horizon is reached.
    
    One-to-one with PredictionRecord (unique constraint on prediction_id).
    Every prediction eventually gets exactly one outcome.
    """
    __tablename__ = "prediction_outcome"
    
    id                       = Column(CHAR(36), primary_key=True, default=new_uuid)
    prediction_id            = Column(CHAR(36), ForeignKey("prediction_record.id",
                                       ondelete="CASCADE"), nullable=False, unique=True)
    evaluation_timestamp     = Column(DateTime, nullable=False, index=True)
    actual_price_start       = Column(Float, nullable=False)
    actual_price_end         = Column(Float, nullable=False)
    actual_return_pct        = Column(Float, nullable=False)
    prediction_accuracy_score = Column(Float, nullable=True)
    is_direction_correct     = Column(Boolean, nullable=False)
    absolute_error           = Column(Float, nullable=False)
    evaluation_status        = Column(String(20), nullable=False, index=True)  # pending, completed, failed
    created_at               = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    prediction   = relationship("PredictionRecord", back_populates="outcome")
    attributions = relationship("PredictionAttribution", back_populates="outcome",
                                cascade="all, delete-orphan")


# =============================================================
# SECTION 2: EVENT TRACKING & ATTRIBUTION
# =============================================================

class MarketEvent(Base):
    """
    News and events that might impact predictions.
    Ingested from news pipeline, stored with embeddings for RAG matching.
    
    WHY TRACK EVENTS?
    When a prediction fails, we need to know WHY. Was it earnings?
    A Fed announcement? Supply chain issues? This table stores events
    so the AI can attribute prediction deltas to real-world causes.
    """
    __tablename__ = "market_event"
    
    id                = Column(CHAR(36), primary_key=True, default=new_uuid)
    event_timestamp   = Column(DateTime, nullable=False, index=True)
    event_type        = Column(String(50), nullable=False, index=True)  # earnings, fed_announcement, etc.
    title             = Column(String(500), nullable=False)
    description       = Column(Text, nullable=True)
    source            = Column(String(200), nullable=True)
    affected_sectors  = Column(JSON, nullable=True)   # ["Technology", "Healthcare"]
    affected_tickers  = Column(JSON, nullable=True)   # ["AAPL", "MSFT"]
    sentiment_score   = Column(Float, nullable=True)  # -1.0 to 1.0
    embedding_vector  = Column(BLOB, nullable=True)   # ChromaDB-compatible bytes
    created_at        = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    attributions = relationship("PredictionAttribution", back_populates="event",
                                cascade="all, delete-orphan")


class PredictionAttribution(Base):
    """
    Links market events to prediction performance deltas.
    AI analyzes which events explain why a prediction was right or wrong.
    
    ATTRIBUTION SCORE:
    0.0 to 1.0, represents how much this event explains the delta.
    Multiple events can contribute. Example:
      Prediction: AAPL +5%
      Actual: AAPL -3%
      Delta: -8%
      
      Attributions:
      - Fed rate hike: 0.7 (major contributor)
      - Supply chain issue: 0.3 (minor contributor)
    """
    __tablename__ = "prediction_attribution"
    
    id                = Column(CHAR(36), primary_key=True, default=new_uuid)
    prediction_id     = Column(CHAR(36), ForeignKey("prediction_record.id",
                                ondelete="CASCADE"), nullable=False, index=True)
    outcome_id        = Column(CHAR(36), ForeignKey("prediction_outcome.id",
                                ondelete="CASCADE"), nullable=False, index=True)
    event_id          = Column(CHAR(36), ForeignKey("market_event.id",
                                ondelete="CASCADE"), nullable=False, index=True)
    attribution_score = Column(Float, nullable=False)  # 0.0 to 1.0
    explanation       = Column(Text, nullable=True)    # AI reasoning
    created_at        = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    prediction = relationship("PredictionRecord", back_populates="attributions")
    outcome    = relationship("PredictionOutcome", back_populates="attributions")
    event      = relationship("MarketEvent", back_populates="attributions")


# =============================================================
# SECTION 3: SELF-CALIBRATION
# =============================================================

class CalibrationProfile(Base):
    """
    Tracks systematic biases by sector/asset class.
    AI detects patterns of over/under-prediction and computes correction factors.
    
    BIAS EXAMPLES:
    - optimism_bias: Consistently over-predicting returns
    - volatility_underestimation: Missing large swings
    - bear_market_blindness: Not seeing downturns
    - sector_specific_overconfidence: Always wrong on biotech
    
    CORRECTION FACTOR:
    Multiplicative adjustment applied to future predictions:
      adjusted_return = predicted_return * correction_factor
    
    Only applied when active=True and sample_size is sufficient.
    """
    __tablename__ = "calibration_profile"
    
    __table_args__ = (
        Index("ix_calibration_sector_active", "sector", "active"),
        Index("ix_calibration_class_active", "asset_class", "active"),
    )
    
    id                  = Column(CHAR(36), primary_key=True, default=new_uuid)
    sector              = Column(String(100), nullable=True, index=True)
    asset_class         = Column(String(50), nullable=True, index=True)
    bias_type           = Column(String(100), nullable=False)
    detected_at         = Column(DateTime, nullable=False)
    sample_size         = Column(Integer, nullable=False)  # Number of predictions analyzed
    bias_magnitude      = Column(Float, nullable=False)
    correction_factor   = Column(Float, nullable=False)
    active              = Column(Boolean, nullable=False, default=True)
    confidence_interval = Column(JSON, nullable=True)      # {"lower": -0.05, "upper": 0.12}
    last_updated        = Column(DateTime, default=datetime.utcnow,
                                 onupdate=datetime.utcnow, nullable=False)


class ModelImprovementLog(Base):
    """
    Tracks prompt evolution and model changes.
    AI rewrites its own analysis prompts based on identified blind spots.
    
    STATUS WORKFLOW:
    1. proposed: AI detected an issue and suggested a fix
    2. testing: New prompt/config is being validated
    3. active: Now in production use
    4. retired: Superseded by newer version
    
    CONFIG STORAGE (JSON):
    Stores entire prompt template + parameters so changes can be
    rolled back or A/B tested.
    """
    __tablename__ = "model_improvement_log"
    
    __table_args__ = (
        Index("ix_improvement_type_status", "improvement_type", "status"),
    )
    
    id                    = Column(CHAR(36), primary_key=True, default=new_uuid)
    improvement_type      = Column(String(50), nullable=False)  # prompt_rewrite, bias_correction, etc.
    detected_issue        = Column(Text, nullable=False)
    old_config            = Column(JSON, nullable=True)
    new_config            = Column(JSON, nullable=False)
    expected_improvement  = Column(Text, nullable=True)
    validation_metrics    = Column(JSON, nullable=True)  # Accuracy before/after, p-value, etc.
    status                = Column(String(20), nullable=False, default="proposed")
    created_at            = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    activated_at          = Column(DateTime, nullable=True)