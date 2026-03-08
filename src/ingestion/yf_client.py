# =============================================================
# src/ingestion/yf_client.py
#
# Responsible for ONE thing: fetching market data from yfinance
# and returning it as clean Python objects.
#
# Key design decisions explained below:
#
# 1. ASYNC WITH THREADPOOL
#    yfinance is a synchronous library — it makes blocking HTTP
#    calls. If you call it directly in an async FastAPI route,
#    it freezes the entire server while waiting for the response.
#    No other requests can be served. The fix is to run it in a
#    ThreadPoolExecutor — a pool of background threads that
#    handle blocking work without freezing the async event loop.
#
# 2. SEPARATION FROM THE ROUTE
#    The route (analysis.py) should not know HOW data is fetched.
#    It calls fetch_market_snapshot() and gets back a clean object.
#    If we swap yfinance for Bloomberg tomorrow, only this file
#    changes. The route stays identical.
#
# 3. GRACEFUL DEGRADATION
#    Market data APIs are unreliable. yfinance scrapes Yahoo Finance
#    and breaks without warning. Every field is Optional and we
#    never crash on a missing value — we return None and let the
#    AI layer acknowledge the gap.
# =============================================================

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import yfinance as yf
from loguru import logger

from src.api.schemas.investment import MarketSnapshot, BudgetProjection

# ── THREAD POOL ────────────────────────────────────────────────────────────────
# A shared pool of threads for running blocking yfinance calls.
# max_workers=4 means up to 4 simultaneous yfinance fetches can run.
# We share one pool across all requests rather than creating a new one
# per request — creating threads is expensive.

_thread_pool = ThreadPoolExecutor(max_workers=4)


# ── SAFE VALUE HELPER ──────────────────────────────────────────────────────────
# yfinance returns a mix of float, int, None, and sometimes the string "N/A"
# or a numpy float that JSON can't serialise (NaN, Infinity).
# This helper normalises everything to either a clean Python float or None.

def _safe_float(value) -> Optional[float]:
    try:
        result = float(value)
        # JSON has no concept of NaN or Infinity — replace with None
        if result != result:    # NaN check (NaN != NaN is always True)
            return None
        if result in (float("inf"), float("-inf")):
            return None
        return result
    except (TypeError, ValueError):
        return None


# ── CORE FETCH — SYNCHRONOUS (runs in thread pool) ─────────────────────────────
# This is the blocking function that actually calls yfinance.
# It is NEVER called directly from async code — always via
# asyncio.get_event_loop().run_in_executor() below.

def _fetch_ticker_sync(ticker: str) -> dict:
    """
    Fetch raw ticker info from yfinance.
    Returns a dict of raw values — no Pydantic models here,
    because this runs in a thread and we keep threading code
    as simple as possible.
    """
    logger.info(f"Fetching market data for {ticker} via yfinance")

    stock = yf.Ticker(ticker)

    # .info is a dict of ~150 fields from Yahoo Finance.
    # It's the most comprehensive single call yfinance offers.
    # The .get() pattern means missing keys return None, not KeyError.
    info = stock.info

    return {
        "ticker":               ticker,
        "company_name":         info.get("longName") or info.get("shortName"),
        "sector":               info.get("sector"),
        "industry":             info.get("industry"),
        "current_price":        info.get("currentPrice") or info.get("regularMarketPrice"),
        "currency":             info.get("currency"),
        "market_cap":           info.get("marketCap"),
        "pe_ratio":             info.get("trailingPE"),
        "forward_pe":           info.get("forwardPE"),
        "pb_ratio":             info.get("priceToBook"),
        "dividend_yield":       info.get("dividendYield"),
        "fifty_two_week_high":  info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low":   info.get("fiftyTwoWeekLow"),
        "avg_volume":           info.get("averageVolume"),
        "beta":                 info.get("beta"),
        "analyst_target_price": info.get("targetMeanPrice"),
    }


# ── ASYNC WRAPPER ──────────────────────────────────────────────────────────────
# This is the function your route calls.
# run_in_executor submits _fetch_ticker_sync to the thread pool and
# immediately returns control to the async event loop. The event loop
# can serve other requests while the thread does the blocking yfinance work.
# When the thread finishes, the event loop resumes this coroutine with the result.

async def fetch_market_snapshot(ticker: str) -> MarketSnapshot:
    """
    Async entry point for fetching market data.
    Runs the blocking yfinance call in a thread pool so it
    doesn't freeze the FastAPI event loop.
    """
    loop = asyncio.get_event_loop()

    try:
        raw = await loop.run_in_executor(
            _thread_pool,
            _fetch_ticker_sync,
            ticker,
        )
    except Exception as e:
        # If yfinance fails entirely (bad ticker, network error, Yahoo
        # rate limit), return a minimal snapshot rather than crashing.
        # The route will detect the missing fields and handle accordingly.
        logger.error(f"yfinance fetch failed for {ticker}: {e}")
        return MarketSnapshot(ticker=ticker)

    # Convert raw dict → Pydantic model, sanitising every numeric field
    return MarketSnapshot(
        ticker              = raw["ticker"],
        company_name        = raw.get("company_name"),
        sector              = raw.get("sector"),
        industry            = raw.get("industry"),
        current_price       = _safe_float(raw.get("current_price")),
        currency            = raw.get("currency"),
        market_cap          = _safe_float(raw.get("market_cap")),
        pe_ratio            = _safe_float(raw.get("pe_ratio")),
        forward_pe          = _safe_float(raw.get("forward_pe")),
        pb_ratio            = _safe_float(raw.get("pb_ratio")),
        dividend_yield      = _safe_float(raw.get("dividend_yield")),
        fifty_two_week_high = _safe_float(raw.get("fifty_two_week_high")),
        fifty_two_week_low  = _safe_float(raw.get("fifty_two_week_low")),
        avg_volume          = _safe_float(raw.get("avg_volume")),
        beta                = _safe_float(raw.get("beta")),
        analyst_target_price= _safe_float(raw.get("analyst_target_price")),
    )


# ── BUDGET PROJECTION ──────────────────────────────────────────────────────────
# Given a ticker and budget, estimate future value using historical returns.
# This is a statistical estimate — Compound Annual Growth Rate (CAGR) from
# the last 5 years of closing prices, with a standard deviation band.
#
# Why 5 years of history?
# - Too short (1-2 years) is too sensitive to recent bull/bear markets
# - Too long (20 years) includes pre-digital-economy data that may not
#   be representative of how the company behaves today

def _calculate_projection_sync(ticker: str, budget: float, horizon_years: int) -> dict:
    import numpy as np

    stock   = yf.Ticker(ticker)
    hist    = stock.history(period="5y")    # 5 years of daily OHLCV

    if hist.empty or len(hist) < 252:       # 252 = trading days in a year
        logger.warning(f"Insufficient history for {ticker} projection")
        return {}

    # Daily returns: (today's close - yesterday's close) / yesterday's close
    # This gives us a series of small decimals like 0.0023, -0.0041, etc.
    daily_returns = hist["Close"].pct_change().dropna()

    # Annualise: scale daily mean and std to yearly equivalents
    # 252 trading days per year
    annual_mean = float(daily_returns.mean() * 252)
    annual_std  = float(daily_returns.std() * (252 ** 0.5))

    # Compound growth: Final = Principal × (1 + rate)^years
    projected_mid  = budget * ((1 + annual_mean) ** horizon_years)
    projected_high = budget * ((1 + annual_mean + annual_std) ** horizon_years)
    projected_low  = budget * ((1 + annual_mean - annual_std) ** horizon_years)

    return {
        "projected_value_low":       round(max(projected_low, 0), 2),
        "projected_value_mid":       round(projected_mid, 2),
        "projected_value_high":      round(projected_high, 2),
        "assumed_annual_return_pct": round(annual_mean * 100, 2),
    }


async def fetch_budget_projection(
    ticker: str,
    budget: float,
    horizon_years: int,
) -> Optional[BudgetProjection]:
    """
    Async wrapper for the projection calculation.
    Returns None if insufficient historical data is available.
    """
    loop = asyncio.get_event_loop()

    try:
        raw = await loop.run_in_executor(
            _thread_pool,
            _calculate_projection_sync,
            ticker,
            budget,
            horizon_years,
        )
    except Exception as e:
        logger.error(f"Projection failed for {ticker}: {e}")
        return None

    if not raw:
        return None

    return BudgetProjection(
        horizon_years               = horizon_years,
        initial_investment          = budget,
        projected_value_low         = raw["projected_value_low"],
        projected_value_mid         = raw["projected_value_mid"],
        projected_value_high        = raw["projected_value_high"],
        assumed_annual_return_pct   = raw["assumed_annual_return_pct"],
    )