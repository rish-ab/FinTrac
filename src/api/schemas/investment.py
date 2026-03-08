# =============================================================
# src/api/schemas/investment.py
#
# Pydantic models define the SHAPE and RULES of data coming
# in (requests) and going out (responses) through the API.
#
# Think of them as a contract:
#   - The user sends JSON that must match InvestmentQuery
#   - The API sends back JSON that matches InvestmentAnalysisResponse
#
# If the incoming JSON breaks the contract (wrong type, missing
# required field, value out of range), FastAPI automatically
# returns a 422 error with a clear explanation — before your
# route function even runs. You never write "if budget is None"
# defensive checks. Pydantic handles all of that.
# =============================================================

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── ENUMS ──────────────────────────────────────────────────────────────────────
# Enums restrict a field to a fixed set of valid string values.
# If a user sends "YOLO" as their risk_tolerance, Pydantic rejects it
# immediately with a clear error rather than letting it reach your logic.

class RiskTolerance(str, Enum):
    CONSERVATIVE = "conservative"   # capital preservation, bonds, dividends
    MODERATE     = "moderate"       # balanced growth + stability
    AGGRESSIVE   = "aggressive"     # high growth, accepts high volatility
    SPECULATIVE  = "speculative"    # crypto, penny stocks, options — high risk


class AssetClass(str, Enum):
    EQUITY    = "equity"            # stocks
    BOND_GOVT = "bond_govt"         # government bonds (T-bills, gilts)
    BOND_CORP = "bond_corp"         # corporate bonds
    ETF       = "etf"               # exchange traded funds
    FOREX     = "forex"             # currency pairs
    COMMODITY = "commodity"         # oil, gold, wheat
    CRYPTO    = "crypto"            # bitcoin, ethereum etc.


# ── REQUEST SCHEMA ─────────────────────────────────────────────────────────────
# This is what the user sends to the API.
# Field() lets us attach metadata: description, constraints, and examples.
# These show up in the auto-generated docs at /docs — essential for a
# portfolio project because it makes the API self-documenting.

class InvestmentQuery(BaseModel):

    # The ticker symbol — "XOM" for Exxon, "AAPL" for Apple
    # min_length=1 and max_length=10 prevent empty strings and nonsense input
    ticker: str = Field(
        ...,                            # ... means required (no default)
        min_length=1,
        max_length=10,
        description="Stock ticker symbol (e.g. XOM, AAPL, TSLA)",
        examples=["XOM", "AAPL", "GOOGL"],
    )

    # Budget in USD. gt=0 means "greater than zero" — negative investment
    # amounts make no sense and we reject them before any logic runs.
    budget: float = Field(
        ...,
        gt=0,
        description="Investment amount in USD",
        examples=[10000, 5000, 25000],
    )

    # Horizon in years. Optional — if not provided we default to None and
    # handle the 3-30 year range assumption in the analysis logic.
    # ge=1 (greater or equal to 1), le=50 (less or equal to 50)
    horizon_years: Optional[int] = Field(
        default=None,
        ge=1,
        le=50,
        description="Investment horizon in years. If omitted, assumes 3–30 year range.",
        examples=[5, 10, 20],
    )

    # Risk tolerance — uses the enum above. Optional: if not provided
    # we'll infer it from the horizon (long horizon → can tolerate more risk)
    risk_tolerance: Optional[RiskTolerance] = Field(
        default=None,
        description="Your risk appetite. If omitted, inferred from horizon.",
    )

    # Free text question — the natural language part.
    # This is what the AI agent will reason over alongside the market data.
    question: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional natural language question about the investment.",
        examples=[
            "Is this a good long-term hold?",
            "How does this compare to the S&P 500?",
        ],
    )


    # ── VALIDATORS ────────────────────────────────────────────
    # field_validator runs after type coercion. Here we normalise the
    # ticker to uppercase so "xom", "Xom", and "XOM" all work the same.
    # The user shouldn't have to know that tickers are uppercase.

    @field_validator("ticker")
    @classmethod
    def normalise_ticker(cls, v: str) -> str:
        return v.strip().upper()


    # ── CROSS-FIELD VALIDATOR ──────────────────────────────────
    # model_validator runs after ALL fields are validated individually.
    # Use it when a rule involves more than one field at once.
    #
    # Rule: if risk_tolerance is not provided, infer it from horizon_years.
    # This makes the API forgiving — users don't need to understand financial
    # risk categories, they just say "20 years" and we figure it out.

    @model_validator(mode="after")
    def infer_risk_from_horizon(self) -> InvestmentQuery:
        if self.risk_tolerance is None and self.horizon_years is not None:
            if self.horizon_years <= 3:
                self.risk_tolerance = RiskTolerance.CONSERVATIVE
            elif self.horizon_years <= 7:
                self.risk_tolerance = RiskTolerance.MODERATE
            elif self.horizon_years <= 15:
                self.risk_tolerance = RiskTolerance.AGGRESSIVE
            else:
                # 15+ years: time horizon is long enough to ride out volatility
                self.risk_tolerance = RiskTolerance.AGGRESSIVE
        return self


    # ── MODEL CONFIG ───────────────────────────────────────────
    # json_schema_extra provides an example payload for the /docs UI.
    # When a developer opens /docs they see a pre-filled example they
    # can run immediately — crucial for a portfolio project.

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
# This model represents the raw market data we fetch from yfinance.
# It sits between the fetcher and the response — the route assembles
# the full response by combining this with the AI analysis later.
#
# Optional fields because not every data point is always available
# (e.g. a bond has no P/E ratio, a new listing has no 52-week history).

class MarketSnapshot(BaseModel):
    ticker:             str
    company_name:       Optional[str]   = None
    sector:             Optional[str]   = None
    industry:           Optional[str]   = None
    current_price:      Optional[float] = None
    currency:           Optional[str]   = None
    market_cap:         Optional[float] = None
    pe_ratio:           Optional[float] = None      # Price / Earnings
    forward_pe:         Optional[float] = None      # Expected future P/E
    pb_ratio:           Optional[float] = None      # Price / Book value
    dividend_yield:     Optional[float] = None      # Annual dividend / price
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low:  Optional[float] = None
    avg_volume:         Optional[float] = None
    beta:               Optional[float] = None      # Volatility vs market (1.0 = same as market)
    analyst_target_price: Optional[float] = None   # Consensus analyst price target


# ── BUDGET PROJECTION ──────────────────────────────────────────────────────────
# Given a budget and historical return data, how much could this investment
# be worth over time? This is a simple compound growth estimate — not a
# guarantee. The AI layer will contextualise this with risk and alternatives.

class BudgetProjection(BaseModel):
    horizon_years:      int
    initial_investment: float
    projected_value_low:  float     # pessimistic scenario (e.g. -1 std dev)
    projected_value_mid:  float     # base case (historical average return)
    projected_value_high: float     # optimistic scenario (e.g. +1 std dev)
    assumed_annual_return_pct: float


# ── RESPONSE SCHEMA ────────────────────────────────────────────────────────────
# What the API sends back to the user.
# Combines the validated input, raw market data, projection, and
# a placeholder for the AI verdict (filled in once the agent layer is built).

class InvestmentAnalysisResponse(BaseModel):
    query:          InvestmentQuery
    market_data:    MarketSnapshot
    projection:     Optional[BudgetProjection]  = None

    # These two fields come from the AI agent — stubbed for now
    ai_verdict:     Optional[str]   = None      # "BUY / HOLD / AVOID"
    ai_reasoning:   Optional[str]   = None      # Full AI explanation
    alternatives:   Optional[list]  = None      # Other assets the AI suggests

    # Horizon that was actually used for analysis
    # (either user-supplied or defaulted to the 3-30 year range)
    effective_horizon_min: int = 3
    effective_horizon_max: int = 30