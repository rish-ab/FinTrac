# =============================================================
# src/api/routes/analysis.py
#
# V3 Phase 8: Added /backtest and /backtest-range endpoints.
# Fixed horizon_years to support float throughout.
# =============================================================

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel, Field

from src.db.v3_models import PredictionRecord
from src.ingestion.document_ingester import ingest_filings_for_ticker

from src.api.schemas.investment import (
    InvestmentQuery,
    InvestmentAnalysisResponse,
    MarketSnapshot,
)
from src.ingestion.yf_client_v2 import fetch_market_snapshot, calculate_budget_projection
from src.agent.advisor_agent import get_investment_verdict, get_comparison_verdict


router = APIRouter()


# ── HELPERS ────────────────────────────────────────────────────────────────────

def _horizon_to_string(horizon_years: Optional[float]) -> str:
    if horizon_years is None:
        return '1w'
    if horizon_years < 0.12:
        return '1m'
    elif horizon_years < 0.38:
        return '3m'
    elif horizon_years < 0.75:
        return '6m'
    else:
        years = int(round(horizon_years))
        return f'{max(1, years)}y'


def _horizon_to_timedelta(horizon_years: Optional[float]):
    from datetime import timedelta
    if horizon_years is None:
        return timedelta(weeks=1)
    days = int(horizon_years * 365)
    return timedelta(days=max(7, days))


# ── POST /evaluate ─────────────────────────────────────────────────────────────

@router.post(
    "/evaluate",
    response_model=InvestmentAnalysisResponse,
    summary="Evaluate an investment",
)
async def evaluate_investment(query: InvestmentQuery) -> InvestmentAnalysisResponse:

    logger.info(
        f"Evaluate request | ticker={query.ticker} "
        f"budget={query.budget} horizon={query.horizon_years} risk={query.risk_tolerance}"
    )

    if query.horizon_years is not None:
        horizon_min = query.horizon_years
        horizon_max = query.horizon_years
        projection_horizon = query.horizon_years
    else:
        horizon_min = 3.0
        horizon_max = 30.0
        projection_horizon = 10.0

    market_snapshot, projection = await asyncio.gather(
        fetch_market_snapshot(query.ticker),
        calculate_budget_projection(query.ticker, query.budget, projection_horizon),
    )

    if market_snapshot.company_name is None and market_snapshot.current_price is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticker '{query.ticker}' not found or no data available.",
        )

    verdict = await get_investment_verdict(query, market_snapshot, projection)

    if verdict is not None:
        async def _record_prediction():
            try:
                from datetime import timedelta
                from src.db.session import AsyncSessionFactory

                horizon_str = _horizon_to_string(query.horizon_years)
                horizon_delta = _horizon_to_timedelta(query.horizon_years)
                evaluation_due = datetime.utcnow() + horizon_delta

                calibration_count = 0
                improvement_count = 0
                prompt_version = 'v1.0.0'
                try:
                    from src.engine.calibration_engine import get_calibration_context
                    from src.engine.prompt_evolver import get_active_improvements, get_active_prompt_version
                    profiles = await get_calibration_context(sector=market_snapshot.sector, asset_class='EQUITY')
                    calibration_count = len(profiles)
                    improvements = await get_active_improvements()
                    improvement_count = len(improvements)
                    prompt_version = get_active_prompt_version(improvements)
                except Exception:
                    pass

                async with AsyncSessionFactory() as pred_session:
                    prediction = PredictionRecord(
                        ticker=query.ticker.upper(),
                        prediction_timestamp=datetime.utcnow(),
                        prediction_horizon=horizon_str,
                        predicted_direction=verdict.action.lower(),
                        predicted_return_pct=None,
                        confidence_score=verdict.confidence,
                        analysis_context={
                            'reasoning': verdict.reasoning,
                            'alternatives': [a.model_dump() for a in verdict.alternatives] if verdict.alternatives else [],
                            'market_price': market_snapshot.current_price,
                            'sector': market_snapshot.sector,
                            'user_budget': query.budget,
                            'user_horizon': query.horizon_years,
                            'calibration_corrections_active': calibration_count,
                            'improvement_patches_active': improvement_count,
                        },
                        prompt_version=prompt_version,
                        model_version='mistral:7b',
                        sector=market_snapshot.sector,
                        asset_class='EQUITY',
                        evaluation_status='PENDING',
                        evaluation_due_at=evaluation_due,
                    )
                    pred_session.add(prediction)
                    await pred_session.commit()
                    logger.info(f"V3: Recorded prediction for {query.ticker} (horizon={horizon_str})")
            except Exception as e:
                logger.error(f"V3: Failed to record prediction: {e}")

        asyncio.create_task(_record_prediction())

    async def _background_ingest():
        from src.db.session import AsyncSessionFactory
        from src.db.asset_seeder import ensure_asset_exists
        async with AsyncSessionFactory() as bg_session:
            try:
                await ensure_asset_exists(market_snapshot, bg_session)
                await ingest_filings_for_ticker(query.ticker, bg_session, max_filings=3)
            except Exception as e:
                logger.error(f"Background ingest failed for {query.ticker}: {e}")

    asyncio.create_task(_background_ingest())

    return InvestmentAnalysisResponse(
        query=query, market_data=market_snapshot, projection=projection,
        effective_horizon_min=horizon_min, effective_horizon_max=horizon_max,
        ai_verdict=verdict.action if verdict else None,
        ai_reasoning=verdict.reasoning if verdict else None,
        alternatives=[a.model_dump() for a in verdict.alternatives] if verdict else None,
    )


# ── GET /snapshot ──────────────────────────────────────────────────────────────

@router.get("/snapshot", response_model=MarketSnapshot, summary="Fetch raw market snapshot")
async def get_snapshot(
    ticker: str = Query(..., min_length=1, max_length=20, examples=["XOM"]),
) -> MarketSnapshot:
    ticker = ticker.strip().upper()
    snapshot = await fetch_market_snapshot(ticker)
    if snapshot.company_name is None and snapshot.current_price is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found.")
    return snapshot


# ── POST /compare ──────────────────────────────────────────────────────────────

@router.post("/compare", summary="Compare multiple assets")
async def compare_assets(
    tickers: list[str],
    budget: float = Query(..., gt=0),
    horizon_years: Optional[float] = Query(default=None, ge=0.08, le=50),
) -> dict:
    if len(tickers) < 2:
        raise HTTPException(422, detail="Provide at least 2 tickers to compare.")
    if len(tickers) > 8:
        raise HTTPException(422, detail="Maximum 8 tickers per comparison.")

    tickers = [t.strip().upper() for t in tickers]
    snapshots = await asyncio.gather(*[fetch_market_snapshot(t) for t in tickers])

    verdict = await get_comparison_verdict(
        snapshots=list(snapshots), budget=budget,
        horizon_years=int(horizon_years) if horizon_years and horizon_years >= 1 else None,
        risk_tolerance=None,
    )

    return {
        "tickers": tickers, "budget": budget, "horizon_years": horizon_years,
        "snapshots": [s.model_dump() for s in snapshots],
        "ai_comparison": verdict.model_dump() if verdict else None,
    }


# =============================================================
# V3 PHASE 8: BACKTEST ENDPOINTS
# =============================================================

class BacktestRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    date: str = Field(..., description="ISO date string, e.g. '2025-01-15'")
    budget: float = Field(default=10000, gt=0)
    horizon: str = Field(default="1m", description="Horizon: 1m, 3m, 6m, 1y, etc.")


class BacktestRangeRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    start_date: str = Field(..., description="Start date, e.g. '2024-01-01'")
    end_date: str = Field(..., description="End date, e.g. '2025-01-01'")
    interval_days: int = Field(default=30, ge=7, le=365)
    budget: float = Field(default=10000, gt=0)
    horizon: str = Field(default="1m")


@router.post("/backtest", summary="Single-date historical backtest")
async def backtest_single(req: BacktestRequest) -> dict:
    """
    Run the AI against historical data for a specific date.
    Returns the prediction + what actually happened.
    """
    try:
        backtest_date = datetime.fromisoformat(req.date)
    except ValueError:
        raise HTTPException(400, detail=f"Invalid date format: '{req.date}'. Use YYYY-MM-DD.")

    if backtest_date > datetime.now():
        raise HTTPException(400, detail="Backtest date cannot be in the future.")

    from src.engine.backtester import run_single_backtest
    result = await run_single_backtest(
        ticker=req.ticker,
        backtest_date=backtest_date,
        budget=req.budget,
        horizon=req.horizon,
    )

    return result.model_dump()


@router.post("/backtest-range", summary="Date-range historical backtest")
async def backtest_range(req: BacktestRangeRequest) -> dict:
    """
    Run backtests at regular intervals across a date range.
    Returns accuracy curve and aggregate statistics.
    
    WARNING: This endpoint calls the AI once per interval point.
    A 12-month range with 30-day intervals = 12 AI calls.
    Expect 2-5 minutes for a full range backtest.
    """
    try:
        start = datetime.fromisoformat(req.start_date)
        end = datetime.fromisoformat(req.end_date)
    except ValueError:
        raise HTTPException(400, detail="Invalid date format. Use YYYY-MM-DD.")

    if end > datetime.now():
        raise HTTPException(400, detail="End date cannot be in the future.")
    if start >= end:
        raise HTTPException(400, detail="Start date must be before end date.")

    from src.engine.backtester import run_range_backtest
    result = await run_range_backtest(
        ticker=req.ticker,
        start_date=start,
        end_date=end,
        interval_days=req.interval_days,
        budget=req.budget,
        horizon=req.horizon,
    )

    return result.model_dump()
