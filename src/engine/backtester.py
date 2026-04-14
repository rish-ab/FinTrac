# =============================================================
# src/engine/backtester.py
#
# FinTrac V3 — Phase 8: Historical Backtesting Engine
#
# WHAT THIS DOES:
# Feeds historical market data to the AI as if it were live,
# captures the prediction, then compares it with what actually
# happened. This validates the AI's decision-making on real
# past scenarios where the outcome is already known.
#
# TWO MODES:
#   1. Single-date backtest: "What would the AI have said about
#      AAPL on 2025-01-15?" → prediction + actual outcome
#   2. Range backtest: "Run backtests on AAPL every month from
#      2024-06-01 to 2025-06-01" → accuracy curve over time
#
# WHY NOT JUST USE THE PREDICTION EVALUATOR?
# The evaluator only works on predictions that were actually made
# by users in real time. The backtester fabricates historical
# scenarios to stress-test the AI on past data — including dates
# before the system was even deployed.
#
# LIMITATIONS:
# - Uses the CURRENT prompt/calibration config, not the config
#   that would have existed at that historical date
# - yfinance historical data availability varies by ticker
# - SEC filings and RAG context are NOT historically scoped
#   (the AI sees current filings, not filings from the backtest date)
# =============================================================

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import yfinance as yf
from loguru import logger
from pydantic import BaseModel

from src.api.schemas.investment import MarketSnapshot, BudgetProjection
from src.ingestion.asset_registry import (
    resolve_ticker, get_asset_display_name, AssetClass
)


# ── THREAD POOL ────────────────────────────────────────────────────────────────

_thread_pool = ThreadPoolExecutor(max_workers=2)


# ── RESPONSE MODELS ───────────────────────────────────────────────────────────

class BacktestResult(BaseModel):
    ticker: str
    backtest_date: str              # ISO date the backtest was run for
    horizon_label: str              # "1m", "3m", "1y" etc.
    
    # Historical snapshot at backtest_date
    price_at_prediction: Optional[float] = None
    
    # AI prediction
    ai_verdict: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_reasoning: Optional[str] = None
    
    # Actual outcome (since we know the future)
    price_at_evaluation: Optional[float] = None
    actual_return_pct: Optional[float] = None
    
    # Accuracy
    direction_correct: Optional[bool] = None
    
    # Meta
    error: Optional[str] = None


class BacktestRangeResult(BaseModel):
    ticker: str
    start_date: str
    end_date: str
    horizon_label: str
    total_backtests: int
    successful: int
    correct: int
    accuracy_pct: float
    avg_confidence: float
    avg_actual_return: float
    results: List[BacktestResult]


# ── HISTORICAL DATA FETCH ─────────────────────────────────────────────────────

def _fetch_historical_snapshot(
    ticker: str,
    target_date: datetime,
) -> Optional[Dict]:
    """
    Fetch market data as it appeared on target_date.
    Returns a dict with price and basic info, or None if unavailable.
    """
    try:
        yf_symbol, asset_class, metadata = resolve_ticker(ticker)
        ticker_obj = yf.Ticker(yf_symbol)
        
        # Fetch a window around the target date (±5 days for weekends)
        start = target_date - timedelta(days=7)
        end = target_date + timedelta(days=3)
        hist = ticker_obj.history(start=start, end=end)
        
        if hist.empty:
            return None
        
        # Find the closest trading day <= target_date
        valid_dates = hist.index[hist.index <= target_date.strftime('%Y-%m-%d %H:%M:%S+00:00')]
        if len(valid_dates) == 0:
            # Try without timezone
            valid_dates = hist.index[hist.index.date <= target_date.date()]
        
        if len(valid_dates) == 0:
            return None
        
        closest_date = valid_dates[-1]
        row = hist.loc[closest_date]
        
        price = float(row['Close'])
        
        # Get company info (static, not date-specific)
        info = ticker_obj.info or {}
        company_name = get_asset_display_name(ticker, asset_class, metadata)
        if asset_class == AssetClass.EQUITY and "longName" in info:
            company_name = info["longName"]
        
        return {
            'price': price,
            'date': closest_date,
            'company_name': company_name,
            'sector': info.get('sector') or (
                'Foreign Exchange' if asset_class == AssetClass.FOREX
                else 'Cryptocurrency' if asset_class == AssetClass.CRYPTO
                else 'Commodities' if asset_class == AssetClass.COMMODITY
                else info.get('sector')
            ),
            'industry': info.get('industry', ''),
            'market_cap': info.get('marketCap'),
            'pe_ratio': info.get('trailingPE'),
            'beta': info.get('beta'),
            'asset_class': asset_class,
            'yf_symbol': yf_symbol,
        }
    
    except Exception as e:
        logger.error(f"Backtest: failed to fetch historical data for {ticker} at {target_date}: {e}")
        return None


def _fetch_future_price(
    yf_symbol: str,
    from_date: datetime,
    horizon_days: int,
) -> Optional[float]:
    """
    Fetch the price N days after from_date.
    This is the "answer" — what actually happened.
    Returns None if the date is in the future or data unavailable.
    """
    try:
        target = from_date + timedelta(days=horizon_days)
        
        # Cannot look into the actual future
        if target > datetime.now():
            return None
        
        ticker_obj = yf.Ticker(yf_symbol)
        start = target - timedelta(days=5)
        end = target + timedelta(days=5)
        hist = ticker_obj.history(start=start, end=end)
        
        if hist.empty:
            return None
        
        # Find closest trading day to target
        valid = hist.index[hist.index.date <= target.date()]
        if len(valid) == 0:
            valid = hist.index
        
        closest = valid[-1] if len(valid) > 0 else hist.index[0]
        return float(hist.loc[closest, 'Close'])
    
    except Exception as e:
        logger.error(f"Backtest: failed to fetch future price for {yf_symbol}: {e}")
        return None


# ── HORIZON PARSING ────────────────────────────────────────────────────────────

def _parse_horizon_to_days(horizon: str) -> int:
    """Convert horizon string to days: '1m'→30, '3m'→90, '1y'→365"""
    h = horizon.strip().lower()
    try:
        if h.endswith('d'):
            return int(h[:-1])
        elif h.endswith('w'):
            return int(h[:-1]) * 7
        elif h.endswith('m'):
            return int(h[:-1]) * 30
        elif h.endswith('y'):
            return int(h[:-1]) * 365
        else:
            return 30  # default 1 month
    except ValueError:
        return 30


# ── SINGLE DATE BACKTEST ──────────────────────────────────────────────────────

async def run_single_backtest(
    ticker: str,
    backtest_date: datetime,
    budget: float = 10000,
    horizon: str = '1m',
) -> BacktestResult:
    """
    Run a backtest for a single date.
    
    1. Fetch market data as of backtest_date
    2. Build a MarketSnapshot from historical data
    3. Run the AI agent to get a verdict
    4. Fetch the actual price at backtest_date + horizon
    5. Compare prediction vs reality
    """
    horizon_days = _parse_horizon_to_days(horizon)
    
    # Step 1: Fetch historical data (blocking, run in thread pool)
    loop = asyncio.get_event_loop()
    historical = await loop.run_in_executor(
        _thread_pool, _fetch_historical_snapshot, ticker, backtest_date,
    )
    
    if historical is None:
        return BacktestResult(
            ticker=ticker,
            backtest_date=backtest_date.isoformat()[:10],
            horizon_label=horizon,
            error=f"No historical data available for {ticker} at {backtest_date.date()}",
        )
    
    price_at_prediction = historical['price']
    
    # Step 2: Build a MarketSnapshot from historical data
    snapshot = MarketSnapshot(
        ticker=ticker.upper(),
        company_name=historical['company_name'],
        sector=historical['sector'],
        industry=historical['industry'],
        current_price=price_at_prediction,
        currency="USD",
        market_cap=historical.get('market_cap'),
        pe_ratio=historical.get('pe_ratio'),
        beta=historical.get('beta'),
    )
    
    # Step 3: Get AI verdict
    from src.agent.advisor_agent import get_investment_verdict
    from src.api.schemas.investment import InvestmentQuery
    
    query = InvestmentQuery(
        ticker=ticker,
        budget=budget,
        horizon_years=horizon_days / 365,
    )
    
    verdict = await get_investment_verdict(query, snapshot, None)
    
    if verdict is None:
        return BacktestResult(
            ticker=ticker,
            backtest_date=backtest_date.isoformat()[:10],
            horizon_label=horizon,
            price_at_prediction=price_at_prediction,
            error="AI verdict unavailable (Ollama may be offline)",
        )
    
    # Step 4: Fetch actual outcome
    future_price = await loop.run_in_executor(
        _thread_pool,
        _fetch_future_price,
        historical['yf_symbol'],
        backtest_date,
        horizon_days,
    )
    
    actual_return = None
    direction_correct = None
    
    if future_price is not None and price_at_prediction > 0:
        actual_return = ((future_price - price_at_prediction) / price_at_prediction) * 100
        predicted_up = verdict.action.upper() in ('BUY',)
        actual_up = actual_return > 0
        direction_correct = (predicted_up == actual_up) or verdict.action.upper() == 'HOLD'
    
    return BacktestResult(
        ticker=ticker,
        backtest_date=backtest_date.isoformat()[:10],
        horizon_label=horizon,
        price_at_prediction=round(price_at_prediction, 4),
        ai_verdict=verdict.action,
        ai_confidence=round(verdict.confidence, 3),
        ai_reasoning=verdict.reasoning,
        price_at_evaluation=round(future_price, 4) if future_price else None,
        actual_return_pct=round(actual_return, 2) if actual_return is not None else None,
        direction_correct=direction_correct,
    )


# ── RANGE BACKTEST ────────────────────────────────────────────────────────────

async def run_range_backtest(
    ticker: str,
    start_date: datetime,
    end_date: datetime,
    interval_days: int = 30,
    budget: float = 10000,
    horizon: str = '1m',
    max_points: int = 24,
) -> BacktestRangeResult:
    """
    Run backtests at regular intervals across a date range.
    
    Example: ticker=AAPL, start=2024-01-01, end=2025-01-01, interval=30
    → Runs ~12 backtests, one per month, returns accuracy curve.
    """
    logger.info(
        f"Backtest range: {ticker} from {start_date.date()} to {end_date.date()} "
        f"every {interval_days}d, horizon={horizon}"
    )
    
    # Generate backtest dates
    dates = []
    current = start_date
    while current <= end_date and len(dates) < max_points:
        dates.append(current)
        current += timedelta(days=interval_days)
    
    # Run backtests sequentially (to avoid overwhelming Ollama)
    results = []
    for dt in dates:
        try:
            result = await run_single_backtest(ticker, dt, budget, horizon)
            results.append(result)
            logger.info(
                f"Backtest {dt.date()}: {result.ai_verdict or 'N/A'} "
                f"(correct={result.direction_correct})"
            )
        except Exception as e:
            logger.error(f"Backtest failed for {dt.date()}: {e}")
            results.append(BacktestResult(
                ticker=ticker,
                backtest_date=dt.isoformat()[:10],
                horizon_label=horizon,
                error=str(e),
            ))
    
    # Calculate aggregate statistics
    successful = [r for r in results if r.ai_verdict is not None]
    evaluated = [r for r in successful if r.direction_correct is not None]
    correct = [r for r in evaluated if r.direction_correct]
    
    accuracy = (len(correct) / len(evaluated) * 100) if evaluated else 0
    avg_conf = (
        sum(r.ai_confidence for r in successful if r.ai_confidence) / len(successful)
        if successful else 0
    )
    avg_return = (
        sum(r.actual_return_pct for r in evaluated if r.actual_return_pct is not None) / len(evaluated)
        if evaluated else 0
    )
    
    return BacktestRangeResult(
        ticker=ticker,
        start_date=start_date.isoformat()[:10],
        end_date=end_date.isoformat()[:10],
        horizon_label=horizon,
        total_backtests=len(results),
        successful=len(successful),
        correct=len(correct),
        accuracy_pct=round(accuracy, 1),
        avg_confidence=round(avg_conf, 3),
        avg_actual_return=round(avg_return, 2),
        results=results,
    )
