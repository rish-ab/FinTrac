# =============================================================
# src/api/routes/portfolio.py
#
# Portfolio and Watchlist endpoints — all protected by JWT.
# Every route calls Depends(get_current_user) which:
#   - Verifies the token
#   - Returns the UserIdentity ORM object
#   - Scopes all DB queries to that user's data
#
# IMPORTANT SECURITY PATTERN:
# Every query filters by user_id = current_user.id
# This prevents user A from reading or modifying user B's data
# even if they guess the correct portfolio UUID.
# =============================================================

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.portfolio import (
    PortfolioCreate, PortfolioResponse,
    WatchlistCreate, WatchlistResponse,
)
from src.core.dependencies import get_current_user
from src.db.models import AssetMaster, Portfolio, UserIdentity, Watchlist
from src.db.session import get_db

router = APIRouter()


# =============================================================
# PORTFOLIO ENDPOINTS
# =============================================================

@router.post(
    "/",
    response_model = PortfolioResponse,
    status_code    = status.HTTP_201_CREATED,
    summary        = "Create a portfolio",
)
async def create_portfolio(
    body:         PortfolioCreate,
    current_user: UserIdentity  = Depends(get_current_user),
    db:           AsyncSession  = Depends(get_db),
) -> PortfolioResponse:

    portfolio = Portfolio(
        user_id       = current_user.id,
        name          = body.name,
        base_currency = body.base_currency,
        objective     = body.objective,
    )
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)

    logger.info(
        f"Portfolio created: '{portfolio.name}' "
        f"for user {current_user.email}"
    )
    return PortfolioResponse.model_validate(portfolio)


@router.get(
    "/",
    response_model = List[PortfolioResponse],
    summary        = "List all portfolios",
)
async def list_portfolios(
    current_user: UserIdentity = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
) -> List[PortfolioResponse]:

    result = await db.execute(
        select(Portfolio)
        .where(Portfolio.user_id == current_user.id)
        .order_by(Portfolio.created_at.desc())
    )
    portfolios = result.scalars().all()
    return [PortfolioResponse.model_validate(p) for p in portfolios]


@router.get(
    "/{portfolio_id}",
    response_model = PortfolioResponse,
    summary        = "Get a portfolio by ID",
)
async def get_portfolio(
    portfolio_id: str,
    current_user: UserIdentity = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
) -> PortfolioResponse:

    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id      == portfolio_id,
            Portfolio.user_id == current_user.id,  # ownership check
        )
    )
    portfolio = result.scalar_one_or_none()

    if not portfolio:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail      = "Portfolio not found",
        )

    return PortfolioResponse.model_validate(portfolio)


@router.delete(
    "/{portfolio_id}",
    status_code = status.HTTP_204_NO_CONTENT,
    summary     = "Delete a portfolio",
)
async def delete_portfolio(
    portfolio_id: str,
    current_user: UserIdentity = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
) -> None:

    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id      == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()

    if not portfolio:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail      = "Portfolio not found",
        )

    await db.delete(portfolio)
    await db.commit()
    logger.info(f"Portfolio '{portfolio.name}' deleted by {current_user.email}")


# =============================================================
# WATCHLIST ENDPOINTS
# =============================================================

async def _resolve_asset(ticker: str, db: AsyncSession) -> AssetMaster | None:
    """Look up an asset by ticker. Returns None if not found."""
    result = await db.execute(
        select(AssetMaster)
        .where(AssetMaster.ticker_symbol == ticker.upper())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.post(
    "/watchlist",
    response_model = WatchlistResponse,
    status_code    = status.HTTP_201_CREATED,
    summary        = "Add asset to watchlist",
)
async def add_to_watchlist(
    body:         WatchlistCreate,
    current_user: UserIdentity = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
) -> WatchlistResponse:

    # Look up asset in AssetMaster
    asset = await _resolve_asset(body.ticker, db)
    if not asset:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail      = f"Ticker '{body.ticker}' not found in asset master. "
                          "Run an /evaluate query first to ingest it.",
        )

    # Check for duplicate
    existing = await db.execute(
        select(Watchlist).where(
            Watchlist.user_id  == current_user.id,
            Watchlist.asset_id == asset.asset_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail      = f"{body.ticker} is already on your watchlist",
        )

    watchlist_item = Watchlist(
        user_id                 = current_user.id,
        asset_id                = asset.asset_id,
        portfolio_id            = body.portfolio_id,
        price_trigger_high      = body.price_trigger_high,
        price_trigger_low       = body.price_trigger_low,
        sentiment_trigger_high  = body.sentiment_trigger_high,
        sentiment_trigger_low   = body.sentiment_trigger_low,
    )
    db.add(watchlist_item)
    await db.commit()
    await db.refresh(watchlist_item)

    logger.info(f"{current_user.email} added {body.ticker} to watchlist")

    return WatchlistResponse(
        id                      = watchlist_item.id,
        user_id                 = watchlist_item.user_id,
        ticker                  = asset.ticker_symbol,
        portfolio_id            = watchlist_item.portfolio_id,
        price_trigger_high      = watchlist_item.price_trigger_high,
        price_trigger_low       = watchlist_item.price_trigger_low,
        sentiment_trigger_high  = watchlist_item.sentiment_trigger_high,
        sentiment_trigger_low   = watchlist_item.sentiment_trigger_low,
    )


@router.get(
    "/watchlist",
    response_model = List[WatchlistResponse],
    summary        = "List watchlist",
)
async def list_watchlist(
    current_user: UserIdentity = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
) -> List[WatchlistResponse]:

    result = await db.execute(
        select(Watchlist, AssetMaster.ticker_symbol)
        .join(AssetMaster, Watchlist.asset_id == AssetMaster.asset_id)
        .where(Watchlist.user_id == current_user.id)
        .order_by(Watchlist.id)
    )
    rows = result.all()

    return [
        WatchlistResponse(
            id                      = w.id,
            user_id                 = w.user_id,
            ticker                  = ticker,
            portfolio_id            = w.portfolio_id,
            price_trigger_high      = w.price_trigger_high,
            price_trigger_low       = w.price_trigger_low,
            sentiment_trigger_high  = w.sentiment_trigger_high,
            sentiment_trigger_low   = w.sentiment_trigger_low,
        )
        for w, ticker in rows
    ]


@router.delete(
    "/watchlist/{watchlist_id}",
    status_code = status.HTTP_204_NO_CONTENT,
    summary     = "Remove from watchlist",
)
async def remove_from_watchlist(
    watchlist_id: str,
    current_user: UserIdentity = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
) -> None:

    result = await db.execute(
        select(Watchlist).where(
            Watchlist.id      == watchlist_id,
            Watchlist.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail      = "Watchlist item not found",
        )

    await db.delete(item)
    await db.commit()