# =============================================================
# src/api/schemas/portfolio.py
# =============================================================

from typing import Optional
from pydantic import BaseModel, field_validator


# ── PORTFOLIO ──────────────────────────────────────────────────

class PortfolioCreate(BaseModel):
    name:          str
    base_currency: str = "USD"
    objective:     Optional[str] = None   # GROWTH, INCOME, PRESERVATION

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Portfolio name cannot be empty")
        return v.strip()

    @field_validator("base_currency")
    @classmethod
    def currency_upper(cls, v: str) -> str:
        return v.upper()


class PortfolioResponse(BaseModel):
    id:            str
    user_id:       str
    name:          str
    base_currency: str
    objective:     Optional[str]

    model_config = {"from_attributes": True}


# ── WATCHLIST ──────────────────────────────────────────────────

class WatchlistCreate(BaseModel):
    ticker:                str
    portfolio_id:          Optional[str]   = None
    price_trigger_high:    Optional[float] = None
    price_trigger_low:     Optional[float] = None
    sentiment_trigger_high: Optional[float] = None
    sentiment_trigger_low:  Optional[float] = None

    @field_validator("ticker")
    @classmethod
    def ticker_upper(cls, v: str) -> str:
        return v.strip().upper()


class WatchlistResponse(BaseModel):
    id:                    str
    user_id:               str
    ticker:                str         # joined from AssetMaster
    portfolio_id:          Optional[str]
    price_trigger_high:    Optional[float]
    price_trigger_low:     Optional[float]
    sentiment_trigger_high: Optional[float]
    sentiment_trigger_low:  Optional[float]

    model_config = {"from_attributes": True}