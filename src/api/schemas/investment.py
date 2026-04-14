# =============================================================
# src/api/schemas/investment.py
#
# Pydantic models — SHAPE and RULES of API request/response data.
#
# V3 Phase 7 CHANGE:
# horizon_years changed from Optional[int] to Optional[float]
# with ge=0.08 (~1 month). This enables short-term analysis
# periods: 1M, 3M, 6M alongside the existing yearly options.
# =============================================================

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── ENUMS ──────────────────────────────────────────────────────────────────────

class RiskTolerance(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE     = "moderate"
    AGGRESSIVE   = "aggressive"
    SPECULATIVE  = "speculative"


class AssetClass(str, Enum):
    EQUITY    = "equity"
    BOND_GOVT = "bond_govt"
    BOND_CORP = "bond_corp"
    ETF       = "etf"
    FOREX     = "forex"
    COMMODITY = "commodity"
    CRYPTO    = "crypto"


# ── REQUEST SCHEMA ─────────────────────────────────────────────────────────────

class InvestmentQuery(BaseModel):

    ticker: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Stock ticker symbol (e.g. XOM, AAPL, TSLA)",
        examples=["XOM", "AAPL", "GOOGL"],
    )

    budget: float = Field(
        ...,
        gt=0,
        description="Investment amount in USD",
        examples=[10000, 5000, 25000],
    )

    # V3 Phase 7: Changed from int to float, minimum from 1 to 0.08
    # Supports sub-year horizons: 0.08 (~1M), 0.25 (3M), 0.5 (6M)
    horizon_years: Optional[float] = Field(
        default=None,
        ge=0.08,
        le=50,
        description=(
            "Investment horizon in years. Supports fractions: "
            "0.08 (1 month), 0.25 (3 months), 0.5 (6 months), 1 (1 year), etc. "
            "If omitted, assumes 3-30 year range."
        ),
        examples=[0.25, 1, 5, 10],
    )

    risk_tolerance: Optional[RiskTolerance] = Field(
        default=None,
        description="Your risk appetite. If omitted, inferred from horizon.",
    )

    question: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional natural language question about the investment.",
        examples=[
            "Is this a good long-term hold?",
            "How does this compare to the S&P 500?",
        ],
    )

    @field_validator("ticker")
    @classmethod
    def normalise_ticker(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def infer_risk_from_horizon(self) -> InvestmentQuery:
        if self.risk_tolerance is None and self.horizon_years is not None:
            if self.horizon_years <= 0.5:
                # Sub-6-month: speculative / short-term trading
                self.risk_tolerance = RiskTolerance.SPECULATIVE
            elif self.horizon_years <= 3:
                self.risk_tolerance = RiskTolerance.CONSERVATIVE
            elif self.horizon_years <= 7:
                self.risk_tolerance = RiskTolerance.MODERATE
            elif self.horizon_years <= 15:
                self.risk_tolerance = RiskTolerance.AGGRESSIVE
            else:
                self.risk_tolerance = RiskTolerance.AGGRESSIVE
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "ticker": "XOM",
                "budget": 10000,
                "horizon_years": 10,
                "risk_tolerance": "moderate",
                "question": "Is Exxon a good long term hold given energy transition risks?",
            }
        }
    }


# ── MARKET DATA SNAPSHOT ───────────────────────────────────────────────────────

class MarketSnapshot(BaseModel):
    ticker:             str
    company_name:       Optional[str]   = None
    sector:             Optional[str]   = None
    industry:           Optional[str]   = None
    current_price:      Optional[float] = None
    currency:           Optional[str]   = None
    market_cap:         Optional[float] = None
    pe_ratio:           Optional[float] = None
    forward_pe:         Optional[float] = None
    pb_ratio:           Optional[float] = None
    dividend_yield:     Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low:  Optional[float] = None
    avg_volume:         Optional[float] = None
    beta:               Optional[float] = None
    analyst_target_price: Optional[float] = None


# ── BUDGET PROJECTION ──────────────────────────────────────────────────────────

class BudgetProjection(BaseModel):
    horizon_years:      float           # V3: changed from int to float
    initial_investment: float
    projected_value_low:  float
    projected_value_mid:  float
    projected_value_high: float
    assumed_annual_return_pct: float


# ── RESPONSE SCHEMA ────────────────────────────────────────────────────────────

class InvestmentAnalysisResponse(BaseModel):
    query:          InvestmentQuery
    market_data:    MarketSnapshot
    projection:     Optional[BudgetProjection]  = None

    ai_verdict:     Optional[str]   = None
    ai_reasoning:   Optional[str]   = None
    alternatives:   Optional[list]  = None

    effective_horizon_min: float = 3    # V3: changed from int to float
    effective_horizon_max: float = 30
