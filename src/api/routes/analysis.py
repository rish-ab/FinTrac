# =============================================================
# src/api/routes/analysis.py
#
# This is the HTTP layer — it defines the URL endpoints and
# coordinates the flow between schemas, fetchers, and (later)
# the AI agent.
#
# A route's job is narrow on purpose:
#   1. Receive a validated request (Pydantic handles validation)
#   2. Call the right services to gather data
#   3. Assemble and return the response
#
# It should contain NO business logic. No calculations. No direct
# DB calls. No yfinance imports. Those live in their own modules.
# The route is the coordinator, not the worker.
# =============================================================

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.ingestion.document_ingester import ingest_filings_for_ticker

from src.api.schemas.investment import (
    InvestmentQuery,
    InvestmentAnalysisResponse,
    MarketSnapshot,
)
from src.ingestion.yf_client import fetch_market_snapshot, fetch_budget_projection
from src.agent.advisor_agent import get_investment_verdict, get_comparison_verdict


# ── ROUTER ─────────────────────────────────────────────────────────────────────
# APIRouter is a mini-app that groups related routes.
# main.py mounts it at /api/v1/analysis, so all routes here
# are prefixed with that path automatically.

router = APIRouter()


# ── POST /evaluate ─────────────────────────────────────────────────────────────
# POST because the user is sending structured data (a JSON body).
# GET would also work technically but GET requests shouldn't have bodies
# by HTTP convention — and a query like this is semantically a "create
# analysis session" action, which is what POST means.
#
# response_model tells FastAPI: "serialise the return value using this
# Pydantic model." This means:
#   - Extra fields in your dict are stripped (no data leakage)
#   - The /docs UI shows exactly what shape the response will be
#   - Response validation catches bugs where you return wrong types

@router.post(
    "/evaluate",
    response_model=InvestmentAnalysisResponse,
    summary="Evaluate an investment",
    description=(
        "Given a ticker, budget, and optional horizon, fetch live market data "
        "and return a structured analysis. If no horizon is provided, the "
        "analysis assumes a 3–30 year holding period."
    ),
)
async def evaluate_investment(query: InvestmentQuery) -> InvestmentAnalysisResponse:
    """
    Main analysis endpoint.

    Flow:
        1. Determine the effective horizon (user-supplied or default 3-30 years)
        2. Fetch market snapshot and budget projection concurrently
        3. Assemble the response
        4. (TODO) Pass to AI agent for verdict and reasoning
    """

    logger.info(
        f"Evaluate request | ticker={query.ticker} "
        f"budget={query.budget} "
        f"horizon={query.horizon_years} "
        f"risk={query.risk_tolerance}"
    )

    # ── EFFECTIVE HORIZON ─────────────────────────────────────
    # If the user didn't supply a horizon, we don't pick one number —
    # we keep the range (3 to 30) and run projections at the midpoint.
    # The AI agent will explain the range rather than false-precision
    # on an exact year.

    if query.horizon_years is not None:
        horizon_min = query.horizon_years
        horizon_max = query.horizon_years
        projection_horizon = query.horizon_years
    else:
        horizon_min = 3
        horizon_max = 30
        projection_horizon = 10     # midpoint of 3-30 for the base projection


    # ── CONCURRENT FETCHES ────────────────────────────────────
    # asyncio.gather() runs multiple coroutines at the same time.
    # Without it, we'd wait for the market snapshot to finish before
    # starting the projection fetch — even though they're independent.
    #
    # With gather:
    #   snapshot fetch starts → immediately starts projection fetch
    #   both run in parallel in the thread pool
    #   we wait for BOTH to finish before continuing
    #
    # On a typical query this saves ~1-2 seconds.

    market_snapshot, projection = await asyncio.gather(
        fetch_market_snapshot(query.ticker),
        fetch_budget_projection(query.ticker, query.budget, projection_horizon),
    )

    # ── VALIDATE TICKER ───────────────────────────────────────
    # If yfinance returns a snapshot with no company name and no price,
    # the ticker almost certainly doesn't exist or is delisted.
    # Return a 404 rather than an empty analysis — empty analyses are
    # misleading (the user thinks the request succeeded).

    if market_snapshot.company_name is None and market_snapshot.current_price is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Ticker '{query.ticker}' not found or no data available. "
                "Check the symbol and try again."
            ),
        )

    # ── AI VERDICT ────────────────────────────────────────────
    # Pass the market data to Mistral for analysis.
    # Returns None if Ollama is unreachable — the response still
    # goes out, just without the AI fields populated.
    verdict = await get_investment_verdict(query, market_snapshot, projection)

    # ── SEC INGESTION (background, own session) ───────────────
    # Fired AFTER the verdict so any exception here cannot affect
    # the response. Uses its own DB session — never share the
    # request session with a background task because the request
    # session closes when the response is sent, which would crash
    # the task mid-write and corrupt the DB transaction.
    async def _background_ingest():
        from src.db.session import AsyncSessionFactory
        async with AsyncSessionFactory() as bg_session:
            try:
                await ingest_filings_for_ticker(
                    query.ticker, bg_session, max_filings=3
                )
            except Exception as e:
                logger.error(f"Background SEC ingestion failed for {query.ticker}: {e}")

    asyncio.create_task(_background_ingest())

    return InvestmentAnalysisResponse(
        query               = query,
        market_data         = market_snapshot,
        projection          = projection,
        effective_horizon_min = horizon_min,
        effective_horizon_max = horizon_max,
        ai_verdict          = verdict.action      if verdict else None,
        ai_reasoning        = verdict.reasoning   if verdict else None,
        alternatives        = [a.model_dump() for a in verdict.alternatives] if verdict else None,
    )


# ── GET /snapshot ──────────────────────────────────────────────────────────────
# A lightweight endpoint for just the raw market data with no analysis.
# Useful for the frontend to display a live price card without triggering
# the full AI pipeline.
#
# Query parameters (not a body) because this is a pure read operation —
# it doesn't create anything, it just looks something up. GET is correct here.
# Query() is how FastAPI reads URL parameters: /snapshot?ticker=XOM&budget=10000

@router.get(
    "/snapshot",
    response_model=MarketSnapshot,
    summary="Fetch raw market snapshot",
    description="Returns live market data for a ticker. No AI analysis.",
)
async def get_snapshot(
    ticker: str = Query(
        ...,
        min_length=1,
        max_length=10,
        description="Ticker symbol",
        examples=["XOM"],
    ),
) -> MarketSnapshot:

    ticker = ticker.strip().upper()
    logger.info(f"Snapshot request | ticker={ticker}")

    snapshot = await fetch_market_snapshot(ticker)

    if snapshot.company_name is None and snapshot.current_price is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticker '{ticker}' not found.",
        )

    return snapshot


# ── POST /compare ──────────────────────────────────────────────────────────────
# Compare multiple tickers side by side.
# Fetches all snapshots concurrently — 5 tickers take the same time as 1.
# This feeds directly into COMPARISON_SESSION in the ERD.
#
# This is a POST because the comparison config (budget, horizon, tickers list)
# is structured data that belongs in a body, not a URL.

@router.post(
    "/compare",
    summary="Compare multiple assets",
    description=(
        "Fetch market snapshots for a list of tickers concurrently. "
        "Basis for the AI comparison and COMPARISON_SESSION ERD entity."
    ),
)
async def compare_assets(
    tickers: list[str],
    budget: float = Query(..., gt=0, description="Investment budget in USD"),
    horizon_years: Optional[int] = Query(default=None, ge=1, le=50),
) -> dict:

    if len(tickers) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least 2 tickers to compare.",
        )

    if len(tickers) > 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum 8 tickers per comparison.",
        )

    # Normalise all tickers
    tickers = [t.strip().upper() for t in tickers]

    logger.info(f"Compare request | tickers={tickers} budget={budget}")

    # Fetch all snapshots concurrently — gather scales to N tickers
    snapshots = await asyncio.gather(
        *[fetch_market_snapshot(t) for t in tickers]
    )

    verdict = await get_comparison_verdict(
        snapshots       = list(snapshots),
        budget          = budget,
        horizon_years   = horizon_years,
        risk_tolerance  = None,
    )

    return {
        "tickers":      tickers,
        "budget":       budget,
        "horizon_years": horizon_years,
        "snapshots":    [s.model_dump() for s in snapshots],
        "ai_comparison": verdict.model_dump() if verdict else None,
    }