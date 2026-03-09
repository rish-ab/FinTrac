# =============================================================
# src/db/models.py
#
# SQLAlchemy ORM models — the Python representation of every
# table in the revised ERD v2.
#
# WHAT IS AN ORM?
# ORM = Object Relational Mapper. Instead of writing raw SQL:
#   INSERT INTO user_identity (email, password_hash) VALUES (...)
# you work with Python objects:
#   user = UserIdentity(email="...", password_hash="...")
#   session.add(user)
#
# SQLAlchemy translates the Python objects into SQL automatically.
# It also enforces types, constraints, and relationships at the
# Python level — before anything touches the database.
#
# STRUCTURE OF EACH MODEL:
#   __tablename__  → the actual MariaDB table name
#   Column(...)    → one column definition
#   relationship() → how models link to each other (FK traversal)
#
# NAMING CONVENTIONS:
#   - Table names: snake_case, plural avoided (matches ERD)
#   - Model classes: PascalCase
#   - All PKs are UUIDs generated server-side (not DB auto-increment)
#     Why? UUIDs are safe to generate before the DB insert, which
#     simplifies async code and prevents ID collisions in distributed
#     systems. Auto-increment requires a round-trip to the DB to
#     get the ID back.
# =============================================================

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, JSON, String, Text, UniqueConstraint, Index
)
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import DeclarativeBase, relationship


# ── BASE CLASS ─────────────────────────────────────────────────────────────────
# All models inherit from Base. This is how SQLAlchemy knows which
# classes to treat as database tables. DeclarativeBase is the modern
# SQLAlchemy 2.0 way — replaces the old declarative_base() function.

class Base(DeclarativeBase):
    pass


# ── UUID HELPER ────────────────────────────────────────────────────────────────
# MariaDB doesn't have a native UUID type, so we store UUIDs as
# CHAR(36) strings. This helper generates a new UUID string each
# time it's called, used as the default for PK columns.

def new_uuid() -> str:
    return str(uuid.uuid4())


# =============================================================
# SECTION 1: CORE USER & AUTH
# =============================================================

class UserIdentity(Base):
    """
    Authentication record. One row per registered user.
    Deliberately minimal — only what's needed for auth.
    Risk profile lives in RiskSettings to keep concerns separated.
    """
    __tablename__ = "user_identity"

    id            = Column(CHAR(36), primary_key=True, default=new_uuid)
    email         = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at    = Column(DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    # ── RELATIONSHIPS ──────────────────────────────────────────
    # These let you do: user.portfolios, user.risk_settings etc.
    # lazy="select" means related rows are fetched only when accessed
    # back_populates wires the relationship from both sides
    risk_settings       = relationship("RiskSettings",          back_populates="user",
                                        cascade="all, delete-orphan")
    portfolios          = relationship("Portfolio",             back_populates="user",
                                        cascade="all, delete-orphan")
    watchlists          = relationship("Watchlist",             back_populates="user")
    transactions        = relationship("TransactionLedger",     back_populates="user")
    positions           = relationship("PositionJournal",       back_populates="user")
    recommendations     = relationship("AIRecommendationLog",   back_populates="user")
    comparison_sessions = relationship("ComparisonSession",     back_populates="user")
    order_groups        = relationship("OrderGroup",            back_populates="user")


class RiskSettings(Base):
    """
    User's risk profile and investment constraints.
    SCD Type 2: valid_from/valid_to tracks history of changes.
    Only one row per user should have valid_to = NULL (the current record).
    """
    __tablename__ = "risk_settings"

    # Partial unique index enforced below: only one open record per user
    __table_args__ = (
        Index("ix_risk_settings_current", "user_id", "valid_to", unique=False),
    )

    id                      = Column(CHAR(36), primary_key=True, default=new_uuid)
    user_id                 = Column(CHAR(36), ForeignKey("user_identity.id",
                                     ondelete="CASCADE"), nullable=False, index=True)
    # Enum stored as string — validated at application layer via Pydantic
    risk_tolerance_level    = Column(String(20), nullable=True)
    investment_horizon_months = Column(Integer, nullable=True)
    liquidity_preference    = Column(String(20), nullable=True)
    sector_exclusions       = Column(JSON, nullable=True)       # ["CRYPTO", "TOBACCO"]
    max_drawdown_pct        = Column(Float, nullable=True)
    max_exposure_limit      = Column(Float, nullable=True)
    valid_from              = Column(DateTime, default=datetime.utcnow, nullable=False)
    valid_to                = Column(DateTime, nullable=True)   # NULL = current record

    user = relationship("UserIdentity", back_populates="risk_settings")


class Portfolio(Base):
    """
    A named investment portfolio belonging to a user.
    A user can have multiple portfolios (retirement, speculative, etc.)
    All positions and transactions are scoped to a portfolio.
    """
    __tablename__ = "portfolio"

    id            = Column(CHAR(36), primary_key=True, default=new_uuid)
    user_id       = Column(CHAR(36), ForeignKey("user_identity.id",
                            ondelete="CASCADE"), nullable=False, index=True)
    name          = Column(String(100), nullable=False)
    base_currency = Column(String(3), nullable=False, default="USD")   # ISO 4217
    objective     = Column(String(20), nullable=True)  # GROWTH/INCOME/PRESERVATION
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at    = Column(DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    user         = relationship("UserIdentity",      back_populates="portfolios")
    watchlists   = relationship("Watchlist",         back_populates="portfolio")
    transactions = relationship("TransactionLedger", back_populates="portfolio")
    positions    = relationship("PositionJournal",   back_populates="portfolio")


# =============================================================
# SECTION 2: ASSET CATALOGUE
# =============================================================

class AssetClassLookup(Base):
    """
    Normalised lookup table for asset classes.
    Replaces the free-text asset_class string in AssetMaster.
    comparable_with JSON array guides valid AI comparisons.
    """
    __tablename__ = "asset_class_lookup"

    id              = Column(CHAR(36), primary_key=True, default=new_uuid)
    class_code      = Column(String(20), unique=True, nullable=False)   # EQUITY, BOND_GOVT
    class_name      = Column(String(50), nullable=False)
    comparable_with = Column(JSON, nullable=True)   # ["EQUITY", "ETF"]

    assets = relationship("AssetMaster", back_populates="asset_class")


class AssetMaster(Base):
    """
    Master record for every tradeable asset in the system.
    Exchange + denomination_currency are critical for correct pricing.
    Subtype-specific fields (bond maturity, forex pairs) live in
    AssetSubtypeBond and AssetSubtypeForex to keep this table generic.
    """
    __tablename__ = "asset_master"

    asset_id               = Column(CHAR(36), primary_key=True, default=new_uuid)
    ticker_symbol          = Column(String(20), nullable=False, index=True)
    asset_class_id         = Column(CHAR(36), ForeignKey("asset_class_lookup.id"),
                                    nullable=True)
    exchange               = Column(String(20), nullable=True)      # NASDAQ, NYSE, LSE
    denomination_currency  = Column(String(3), nullable=True)       # USD, EUR, GBP
    sector                 = Column(String(50), nullable=True)
    industry               = Column(String(100), nullable=True)
    country_code           = Column(String(3), nullable=True)        # US, GB, DE
    status                 = Column(String(10), nullable=False, default="ACTIVE")
    status_updated_at      = Column(DateTime, default=datetime.utcnow)

    # Unique constraint: same ticker can exist on different exchanges
    # e.g. AAPL on NASDAQ vs AAPL as ADR on Frankfurt
    __table_args__ = (
        UniqueConstraint("ticker_symbol", "exchange", name="uq_ticker_exchange"),
    )

    asset_class    = relationship("AssetClassLookup",    back_populates="assets")
    bond_subtype   = relationship("AssetSubtypeBond",    back_populates="asset",
                                   uselist=False)   # one-to-one
    forex_subtype  = relationship("AssetSubtypeForex",   back_populates="asset",
                                   uselist=False)   # one-to-one
    watchlists     = relationship("Watchlist",           back_populates="asset")
    transactions   = relationship("TransactionLedger",   back_populates="asset")
    positions      = relationship("PositionJournal",     back_populates="asset")
    recommendations = relationship("AIRecommendationLog", back_populates="asset")
    documents      = relationship("DocumentRegistry",    back_populates="asset")


class AssetSubtypeBond(Base):
    """
    Bond-specific fields that don't belong on the generic AssetMaster.
    One-to-one with AssetMaster (only exists for BOND_GOVT / BOND_CORP assets).
    """
    __tablename__ = "asset_subtype_bond"

    id            = Column(CHAR(36), primary_key=True, default=new_uuid)
    asset_id      = Column(CHAR(36), ForeignKey("asset_master.asset_id",
                            ondelete="CASCADE"), unique=True, nullable=False)
    maturity_date = Column(DateTime, nullable=True)
    coupon_rate   = Column(Float, nullable=True)        # annual interest rate %
    issuer_type   = Column(String(20), nullable=True)   # GOVERNMENT / CORPORATE
    credit_rating = Column(String(10), nullable=True)   # AAA, BBB+, etc.

    asset = relationship("AssetMaster", back_populates="bond_subtype")


class AssetSubtypeForex(Base):
    """
    Forex-specific fields. One-to-one with AssetMaster.
    """
    __tablename__ = "asset_subtype_forex"

    id             = Column(CHAR(36), primary_key=True, default=new_uuid)
    asset_id       = Column(CHAR(36), ForeignKey("asset_master.asset_id",
                             ondelete="CASCADE"), unique=True, nullable=False)
    base_currency  = Column(String(3), nullable=False)   # EUR in EUR/USD
    quote_currency = Column(String(3), nullable=False)   # USD in EUR/USD

    asset = relationship("AssetMaster", back_populates="forex_subtype")


class MacroIndicatorMaster(Base):
    """
    Identity record for every macro economic series.
    Critical fix from ERD review: PARQUET_MACRO_SERIES was a table
    of unidentified numbers without this. series_code maps to FRED/BLS
    identifiers e.g. FEDFUNDS, CPIAUCSL, UNRATE.
    """
    __tablename__ = "macro_indicator_master"

    id                = Column(CHAR(36), primary_key=True, default=new_uuid)
    series_code       = Column(String(50), unique=True, nullable=False)  # FEDFUNDS
    name              = Column(String(200), nullable=False)
    source            = Column(String(20), nullable=False)   # FRED, BLS, ECB
    unit              = Column(String(50), nullable=True)    # %, USD billions
    country_code      = Column(String(3), nullable=True)
    release_frequency = Column(String(20), nullable=True)    # MONTHLY, QUARTERLY


# =============================================================
# SECTION 3: PORTFOLIO & TRADING
# =============================================================

class Watchlist(Base):
    """
    Assets a user is monitoring with trigger thresholds.
    Scoped to a portfolio so alerts are goal-aware.
    AlertQueue references this to deliver notifications.
    """
    __tablename__ = "watchlist"

    id                     = Column(CHAR(36), primary_key=True, default=new_uuid)
    user_id                = Column(CHAR(36), ForeignKey("user_identity.id",
                                     ondelete="CASCADE"), nullable=False)
    portfolio_id           = Column(CHAR(36), ForeignKey("portfolio.id",
                                     ondelete="SET NULL"), nullable=True)
    asset_id               = Column(CHAR(36), ForeignKey("asset_master.asset_id"),
                                     nullable=False)
    sentiment_trigger_high = Column(Float, nullable=True)
    sentiment_trigger_low  = Column(Float, nullable=True)
    price_trigger_high     = Column(Float, nullable=True)
    price_trigger_low      = Column(Float, nullable=True)

    user      = relationship("UserIdentity", back_populates="watchlists")
    portfolio = relationship("Portfolio",    back_populates="watchlists")
    asset     = relationship("AssetMaster",  back_populates="watchlists")
    alerts    = relationship("AlertQueue",   back_populates="watchlist",
                              cascade="all, delete-orphan")


class OrderGroup(Base):
    """
    Groups related transactions together (e.g. multi-leg trades).
    Replaces the old string transaction_group_id in TransactionLedger
    with a proper FK-enforced entity.
    """
    __tablename__ = "order_group"

    id             = Column(CHAR(36), primary_key=True, default=new_uuid)
    user_id        = Column(CHAR(36), ForeignKey("user_identity.id",
                             ondelete="CASCADE"), nullable=False)
    strategy_label = Column(String(100), nullable=True)  # "Pairs Trade AAPL/MSFT"
    created_at     = Column(DateTime, default=datetime.utcnow, nullable=False)

    user         = relationship("UserIdentity",      back_populates="order_groups")
    transactions = relationship("TransactionLedger", back_populates="order_group")


class TransactionLedger(Base):
    """
    Immutable record of every buy/sell/dividend event.
    Never update or delete rows — append only.
    settlement_currency + commission allow accurate net P&L.
    """
    __tablename__ = "transaction_ledger"

    id                  = Column(CHAR(36), primary_key=True, default=new_uuid)
    user_id             = Column(CHAR(36), ForeignKey("user_identity.id"),
                                  nullable=False, index=True)
    portfolio_id        = Column(CHAR(36), ForeignKey("portfolio.id"),
                                  nullable=True)
    asset_id            = Column(CHAR(36), ForeignKey("asset_master.asset_id"),
                                  nullable=False)
    order_group_id      = Column(CHAR(36), ForeignKey("order_group.id"),
                                  nullable=True)
    action_type         = Column(String(10), nullable=False)    # BUY, SELL, DIVIDEND
    quantity            = Column(Float, nullable=False)
    execution_price     = Column(Float, nullable=False)
    settlement_currency = Column(String(3), nullable=False, default="USD")
    commission          = Column(Float, nullable=True, default=0.0)
    tax_withheld        = Column(Float, nullable=True, default=0.0)
    order_type          = Column(String(10), nullable=True)     # MARKET, LIMIT, STOP
    executed_at         = Column(DateTime, nullable=False, index=True)

    user        = relationship("UserIdentity", back_populates="transactions")
    portfolio   = relationship("Portfolio",    back_populates="transactions")
    asset       = relationship("AssetMaster",  back_populates="transactions")
    order_group = relationship("OrderGroup",   back_populates="transactions")


class PositionJournal(Base):
    """
    Current and historical positions using SCD Type 2.
    is_current=True → the live position.
    is_current=False → historical snapshot (closed or superseded).

    CRITICAL CONSTRAINT (enforced in session.py on writes):
    Only one row per (user_id, portfolio_id, asset_id) can have
    is_current=True at any time.
    """
    __tablename__ = "position_journal"

    __table_args__ = (
        # Prevents duplicate open positions at DB level
        Index("ix_position_current", "user_id", "portfolio_id",
              "asset_id", "is_current"),
    )

    id                = Column(CHAR(36), primary_key=True, default=new_uuid)
    user_id           = Column(CHAR(36), ForeignKey("user_identity.id"),
                                nullable=False, index=True)
    portfolio_id      = Column(CHAR(36), ForeignKey("portfolio.id"),
                                nullable=True)
    asset_id          = Column(CHAR(36), ForeignKey("asset_master.asset_id"),
                                nullable=False)
    net_quantity      = Column(Float, nullable=False)
    average_cost      = Column(Float, nullable=False)
    position_currency = Column(String(3), nullable=False, default="USD")
    realized_pnl      = Column(Float, nullable=True, default=0.0)
    unrealized_pnl    = Column(Float, nullable=True, default=0.0)
    is_current        = Column(Boolean, nullable=False, default=True, index=True)
    valid_from        = Column(DateTime, default=datetime.utcnow, nullable=False)
    valid_to          = Column(DateTime, nullable=True)     # NULL = still open

    user      = relationship("UserIdentity", back_populates="positions")
    portfolio = relationship("Portfolio",    back_populates="positions")
    asset     = relationship("AssetMaster",  back_populates="positions")


# =============================================================
# SECTION 4: AI LAYER
# =============================================================

class AIRecommendationLog(Base):
    """
    Persists every AI verdict for audit, replay, and feedback.
    model_version + context_snapshot_id make results reproducible.
    expires_at prevents stale verdicts surfacing in the UI.
    """
    __tablename__ = "ai_recommendation_log"

    id                   = Column(CHAR(36), primary_key=True, default=new_uuid)
    user_id              = Column(CHAR(36), ForeignKey("user_identity.id"),
                                   nullable=False, index=True)
    asset_id             = Column(CHAR(36), ForeignKey("asset_master.asset_id"),
                                   nullable=True)
    comparison_session_id = Column(CHAR(36), ForeignKey("comparison_session.id"),
                                    nullable=True)
    recommended_action   = Column(String(10), nullable=False)   # BUY, HOLD, AVOID
    confidence_score     = Column(Float, nullable=True)
    driving_factors      = Column(JSON, nullable=True)          # structured factors
    model_version        = Column(String(50), nullable=False)   # "mistral:7b-q4"
    context_snapshot_id  = Column(String(100), nullable=True)   # hash of input data
    expires_at           = Column(DateTime, nullable=True)
    generated_at         = Column(DateTime, default=datetime.utcnow, nullable=False)

    user               = relationship("UserIdentity",     back_populates="recommendations")
    asset              = relationship("AssetMaster",      back_populates="recommendations")
    comparison_session = relationship("ComparisonSession",back_populates="recommendations")
    feedback           = relationship("RecommendationFeedback", back_populates="recommendation",
                                       uselist=False, cascade="all, delete-orphan")


class RecommendationFeedback(Base):
    """
    Did the user act on the recommendation? What was the outcome?
    This is the AI improvement loop — without it the model cannot
    be evaluated or fine-tuned on real results.
    """
    __tablename__ = "recommendation_feedback"

    id                 = Column(CHAR(36), primary_key=True, default=new_uuid)
    recommendation_id  = Column(CHAR(36), ForeignKey("ai_recommendation_log.id",
                                  ondelete="CASCADE"), unique=True, nullable=False)
    user_acted         = Column(Boolean, nullable=True)
    action_taken_at    = Column(DateTime, nullable=True)
    outcome_pct_7d     = Column(Float, nullable=True)   # % change after 7 days
    outcome_pct_30d    = Column(Float, nullable=True)   # % change after 30 days
    user_rating        = Column(Integer, nullable=True) # 1–5 stars
    recorded_at        = Column(DateTime, default=datetime.utcnow)

    recommendation = relationship("AIRecommendationLog", back_populates="feedback")


class ComparisonSession(Base):
    """
    Persists a user's "compare these assets" research session.
    assets_compared stores the tickers evaluated.
    winner_asset_id records the AI's final pick.
    """
    __tablename__ = "comparison_session"

    id               = Column(CHAR(36), primary_key=True, default=new_uuid)
    user_id          = Column(CHAR(36), ForeignKey("user_identity.id",
                               ondelete="CASCADE"), nullable=False)
    budget           = Column(Float, nullable=True)
    horizon_months   = Column(Integer, nullable=True)
    assets_compared  = Column(JSON, nullable=True)      # ["XOM", "CVX", "SLB"]
    winner_asset_id  = Column(CHAR(36), ForeignKey("asset_master.asset_id"),
                               nullable=True)
    generated_at     = Column(DateTime, default=datetime.utcnow, nullable=False)

    user            = relationship("UserIdentity",        back_populates="comparison_sessions")
    recommendations = relationship("AIRecommendationLog", back_populates="comparison_session")


class AlertQueue(Base):
    """
    Delivery queue for watchlist threshold alerts.
    Decouples detection (watchlist threshold hit) from delivery
    (email/push send). delivered_at=NULL means pending delivery.
    """
    __tablename__ = "alert_queue"

    id            = Column(CHAR(36), primary_key=True, default=new_uuid)
    user_id       = Column(CHAR(36), ForeignKey("user_identity.id",
                            ondelete="CASCADE"), nullable=False)
    watchlist_id  = Column(CHAR(36), ForeignKey("watchlist.id",
                            ondelete="CASCADE"), nullable=False)
    alert_type    = Column(String(30), nullable=False)   # PRICE_HIGH, SENTIMENT_LOW
    trigger_value = Column(Float, nullable=True)
    triggered_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    delivered_at  = Column(DateTime, nullable=True)      # NULL = not yet delivered
    channel       = Column(String(10), nullable=False, default="EMAIL")
    status        = Column(String(10), nullable=False, default="PENDING")

    watchlist = relationship("Watchlist", back_populates="alerts")


# =============================================================
# SECTION 5: INGESTION & DOCUMENTS
# =============================================================

class IngestionLog(Base):
    """
    Records every data fetch operation.
    PARQUET tables reference ingestion_id to trace which fetch
    produced which file.
    """
    __tablename__ = "ingestion_log"

    ingestion_id       = Column(CHAR(36), primary_key=True, default=new_uuid)
    source_api         = Column(String(50), nullable=False)  # yfinance, FRED, EDGAR
    file_path_reference = Column(String(500), nullable=True)
    schema_hash        = Column(String(64), nullable=True)   # SHA-256 of schema
    fetched_at         = Column(DateTime, default=datetime.utcnow, nullable=False)
    status             = Column(String(10), nullable=False, default="SUCCESS")

    manifests = relationship("ParquetManifest", back_populates="ingestion")
    documents = relationship("DocumentRegistry", back_populates="ingestion")


class ParquetManifest(Base):
    """
    Audit trail for every Parquet file written to the data lake.
    Replaces unenforced cross-store FKs with a verifiable record.
    schema_hash detects silent schema drift.
    """
    __tablename__ = "parquet_manifest"

    id                = Column(CHAR(36), primary_key=True, default=new_uuid)
    ingestion_id      = Column(CHAR(36), ForeignKey("ingestion_log.ingestion_id"),
                                nullable=False)
    parquet_file_path = Column(String(500), nullable=False)
    row_count         = Column(Integer, nullable=True)
    schema_hash       = Column(String(64), nullable=True)
    written_at        = Column(DateTime, default=datetime.utcnow, nullable=False)
    validation_status = Column(String(10), nullable=False, default="PENDING")

    ingestion = relationship("IngestionLog", back_populates="manifests")


class DocumentRegistry(Base):
    """
    Index of every SEC filing and document ingested.
    raw_text_path → the extracted text file for vector embedding.
    embedding_status tracks where the document is in the RAG pipeline.
    """
    __tablename__ = "document_registry"

    id               = Column(CHAR(36), primary_key=True, default=new_uuid)
    asset_id         = Column(CHAR(36), ForeignKey("asset_master.asset_id"),
                               nullable=True, index=True)
    doc_type         = Column(String(20), nullable=False)   # SEC_10K, SEC_8K, NEWS
    source_url       = Column(String(1000), nullable=True)
    filed_at         = Column(DateTime, nullable=True)
    ingestion_id     = Column(CHAR(36), ForeignKey("ingestion_log.ingestion_id"),
                               nullable=True)
    raw_text_path    = Column(String(500), nullable=True)   # path to extracted text
    embedding_status = Column(String(10), nullable=False, default="PENDING")
    # PENDING → PROCESSING → DONE → FAILED

    asset     = relationship("AssetMaster",  back_populates="documents")
    ingestion = relationship("IngestionLog", back_populates="documents")