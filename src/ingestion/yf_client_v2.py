# =============================================================
# src/ingestion/yf_client_v2.py
#
# Multi-asset yfinance client
# Handles equities, FOREX, bonds, commodities, crypto, indices
#
# V3 Phase 8: horizon_years changed from int to float to support
# sub-year horizons (0.08 = 1 month, 0.25 = 3 months).
# =============================================================

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional

import yfinance as yf
from loguru import logger

from src.api.schemas.investment import MarketSnapshot, BudgetProjection
from src.ingestion.asset_registry import (
    resolve_ticker,
    get_asset_display_name,
    get_projection_params,
    AssetClass,
)


_thread_pool = ThreadPoolExecutor(max_workers=3)


# ── FETCH MARKET DATA ──────────────────────────────────────────────────────────

def _fetch_ticker_sync(user_input: str) -> Optional[MarketSnapshot]:
    """Synchronous fetch — runs in thread pool."""
    try:
        yf_symbol, asset_class, metadata = resolve_ticker(user_input)
        
        logger.info(
            f"Fetching market data for {user_input} "
            f"(resolved to {yf_symbol}, class: {asset_class})"
        )
        
        ticker_obj = yf.Ticker(yf_symbol)
        info = ticker_obj.info
        
        if not info or "symbol" not in info:
            logger.warning(f"No data available for {yf_symbol}")
            return None
        
        company_name = get_asset_display_name(user_input, asset_class, metadata)
        if asset_class == AssetClass.EQUITY and "longName" in info:
            company_name = info["longName"]
        
        snapshot = _build_snapshot(
            ticker=user_input.upper(),
            yf_symbol=yf_symbol,
            asset_class=asset_class,
            info=info,
            company_name=company_name,
            metadata=metadata,
        )
        
        return snapshot
    
    except Exception as e:
        logger.error(f"Failed to fetch {user_input}: {e}")
        return None


def _build_snapshot(
    ticker: str,
    yf_symbol: str,
    asset_class: AssetClass,
    info: dict,
    company_name: str,
    metadata: dict,
) -> MarketSnapshot:
    """Build MarketSnapshot from yfinance info dict."""
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    currency = info.get("currency", "USD")
    
    if asset_class == AssetClass.EQUITY:
        return MarketSnapshot(
            ticker=ticker,
            company_name=company_name,
            sector=info.get("sector"),
            industry=info.get("industry"),
            current_price=current_price,
            currency=currency,
            market_cap=info.get("marketCap"),
            pe_ratio=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            pb_ratio=info.get("priceToBook"),
            dividend_yield=info.get("dividendYield"),
            fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
            fifty_two_week_low=info.get("fiftyTwoWeekLow"),
            avg_volume=info.get("averageVolume"),
            beta=info.get("beta"),
            analyst_target_price=info.get("targetMeanPrice"),
        )
    
    elif asset_class == AssetClass.FOREX:
        return MarketSnapshot(
            ticker=ticker,
            company_name=company_name,
            sector="Foreign Exchange",
            industry=f"{metadata.get('base', '???')} / {metadata.get('quote', '???')}",
            current_price=current_price,
            currency=metadata.get("quote", "USD"),
            market_cap=None,
            pe_ratio=None, forward_pe=None, pb_ratio=None, dividend_yield=None,
            fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
            fifty_two_week_low=info.get("fiftyTwoWeekLow"),
            avg_volume=info.get("averageVolume"),
            beta=None, analyst_target_price=None,
        )
    
    elif asset_class == AssetClass.BOND:
        return MarketSnapshot(
            ticker=ticker,
            company_name=company_name,
            sector="Fixed Income",
            industry=f"US Treasury {metadata.get('maturity', '')}",
            current_price=current_price,
            currency="USD",
            market_cap=None, pe_ratio=None, forward_pe=None,
            pb_ratio=None, dividend_yield=None,
            fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
            fifty_two_week_low=info.get("fiftyTwoWeekLow"),
            avg_volume=None, beta=None, analyst_target_price=None,
        )
    
    elif asset_class == AssetClass.COMMODITY:
        return MarketSnapshot(
            ticker=ticker,
            company_name=company_name,
            sector="Commodities",
            industry=metadata.get("sector", "Commodity"),
            current_price=current_price,
            currency="USD",
            market_cap=None, pe_ratio=None, forward_pe=None,
            pb_ratio=None, dividend_yield=None,
            fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
            fifty_two_week_low=info.get("fiftyTwoWeekLow"),
            avg_volume=info.get("averageVolume"),
            beta=None, analyst_target_price=None,
        )
    
    elif asset_class == AssetClass.CRYPTO:
        return MarketSnapshot(
            ticker=ticker,
            company_name=company_name,
            sector="Cryptocurrency",
            industry="Digital Asset",
            current_price=current_price,
            currency="USD",
            market_cap=info.get("marketCap"),
            pe_ratio=None, forward_pe=None, pb_ratio=None, dividend_yield=None,
            fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
            fifty_two_week_low=info.get("fiftyTwoWeekLow"),
            avg_volume=info.get("averageVolume"),
            beta=None, analyst_target_price=None,
        )
    
    elif asset_class == AssetClass.INDEX:
        return MarketSnapshot(
            ticker=ticker,
            company_name=company_name,
            sector="Market Index",
            industry=metadata.get("name", "Index"),
            current_price=current_price,
            currency=currency,
            market_cap=None,
            pe_ratio=info.get("trailingPE"),
            forward_pe=None, pb_ratio=None, dividend_yield=None,
            fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
            fifty_two_week_low=info.get("fiftyTwoWeekLow"),
            avg_volume=info.get("averageVolume"),
            beta=None, analyst_target_price=None,
        )
    
    else:
        return MarketSnapshot(
            ticker=ticker, company_name=company_name,
            current_price=current_price, currency=currency,
        )


async def fetch_market_snapshot(ticker: str) -> Optional[MarketSnapshot]:
    """Async wrapper for multi-asset market data fetch."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_thread_pool, _fetch_ticker_sync, ticker)


# ── BUDGET PROJECTION ──────────────────────────────────────────────────────────

def _calculate_projection_sync(
    ticker: str,
    initial_investment: float,
    horizon_years: float,           # V3 Phase 8: float, not int
) -> Optional[BudgetProjection]:
    """Calculate budget projection with asset-specific parameters."""
    try:
        yf_symbol, asset_class, _ = resolve_ticker(ticker)
        params = get_projection_params(asset_class)
        
        ticker_obj = yf.Ticker(yf_symbol)
        
        # Lookback: at least 6 months, at most 5 years
        lookback_years = max(0.5, min(horizon_years, 5))
        end_date = datetime.now()
        start_date = end_date - timedelta(days=int(lookback_years * 365) + 30)
        
        hist = ticker_obj.history(start=start_date, end=end_date)
        
        if hist.empty or len(hist) < 20:
            logger.warning(f"Insufficient historical data for {ticker}")
            return None
        
        start_price = hist["Close"].iloc[0]
        end_price = hist["Close"].iloc[-1]
        years_actual = len(hist) / 252
        
        cagr = ((end_price / start_price) ** (1 / years_actual) - 1) * 100
        
        # Asset-specific bounds
        if asset_class == AssetClass.FOREX:
            cagr = max(min(cagr, 5.0), -5.0)
        elif asset_class == AssetClass.BOND:
            cagr = max(min(cagr, 8.0), -2.0)
        elif asset_class == AssetClass.CRYPTO:
            cagr = max(min(cagr, 200.0), -80.0)
        
        growth_factor = (1 + cagr / 100) ** horizon_years
        mid_value = initial_investment * growth_factor
        low_value = initial_investment * growth_factor * params["low_multiplier"]
        high_value = initial_investment * growth_factor * params["high_multiplier"]
        
        return BudgetProjection(
            horizon_years=horizon_years,
            initial_investment=initial_investment,
            projected_value_low=low_value,
            projected_value_mid=mid_value,
            projected_value_high=high_value,
            assumed_annual_return_pct=cagr,
        )
    
    except Exception as e:
        logger.error(f"Projection calculation failed for {ticker}: {e}")
        return None


async def calculate_budget_projection(
    ticker: str,
    initial_investment: float,
    horizon_years: float,           # V3 Phase 8: float, not int
) -> Optional[BudgetProjection]:
    """Async wrapper for projection calculation."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _thread_pool,
        _calculate_projection_sync,
        ticker,
        initial_investment,
        horizon_years,
    )
