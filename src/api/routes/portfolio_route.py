# =============================================================
# src/api/routes/portfolio.py
#
# Portfolio, Holdings, and Watchlist endpoints.
# All protected by JWT — scoped to current_user.
#
# V3 Phase 8: Added holdings endpoints:
#   POST /{id}/holdings   — record a buy/sell
#   GET  /{id}/holdings   — list current positions with live P&L
#   DELETE /{id}/holdings/{pos_id} — close a position
# =============================================================

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.portfolio import (
    PortfolioCreate, PortfolioResponse,
    WatchlistCreate, WatchlistResponse,
)
from src.core.dependencies import get_current_user
from src.db.models import (
    AssetMaster, Portfolio, UserIdentity, Watchlist,
    TransactionLedger, PositionJournal,
)
from src.db.session import get_db

router = APIRouter()


# ── HOLDING SCHEMAS ────────────────────────────────────────────

class HoldingCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    action: str = Field(default="BUY", description="BUY or SELL")
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0, description="Execution price per unit")
    notes: Optional[str] = None

    @field_validator("ticker")
    @classmethod
    def ticker_upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("action")
    @classmethod
    def action_valid(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ("BUY", "SELL"):
            raise ValueError("action must be BUY or SELL")
        return v


class HoldingResponse(BaseModel):
    position_id: str
    ticker: str
    quantity: float
    avg_cost: float
    total_cost: float
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    pnl_pct: Optional[float] = None


class PortfolioSummary(BaseModel):
    portfolio: PortfolioResponse
    total_invested: float
    total_current_value: Optional[float]
    total_pnl: Optional[float]
    total_pnl_pct: Optional[float]
    holdings: List[HoldingResponse]


# ── ASSET RESOLVER ─────────────────────────────────────────────

async def _resolve_or_create_asset(ticker: str, db: AsyncSession) -> AssetMaster:
    """Find asset by ticker, or create a minimal record."""
    result = await db.execute(
        select(AssetMaster)
        .where(AssetMaster.ticker_symbol == ticker)
        .limit(1)
    )
    asset = result.scalar_one_or_none()

    if asset:
        return asset

    # Auto-create minimal asset record
    asset = AssetMaster(
        ticker_symbol=ticker,
        denomination_currency="USD",
        status="ACTIVE",
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    logger.info(f"Auto-created AssetMaster for {ticker}")
    return asset


# =============================================================
# PORTFOLIO CRUD
# =============================================================

@router.post("/", response_model=PortfolioResponse, status_code=201, summary="Create a portfolio")
async def create_portfolio(
    body: PortfolioCreate,
    current_user: UserIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    portfolio = Portfolio(
        user_id=current_user.id, name=body.name,
        base_currency=body.base_currency, objective=body.objective,
    )
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    logger.info(f"Portfolio created: '{portfolio.name}' for user {current_user.email}")
    return PortfolioResponse.model_validate(portfolio)


@router.get("/", response_model=List[PortfolioResponse], summary="List all portfolios")
async def list_portfolios(
    current_user: UserIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[PortfolioResponse]:
    result = await db.execute(
        select(Portfolio).where(Portfolio.user_id == current_user.id)
        .order_by(Portfolio.created_at.desc())
    )
    return [PortfolioResponse.model_validate(p) for p in result.scalars().all()]


@router.get("/{portfolio_id}", response_model=PortfolioResponse, summary="Get a portfolio")
async def get_portfolio(
    portfolio_id: str,
    current_user: UserIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == current_user.id)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(404, detail="Portfolio not found")
    return PortfolioResponse.model_validate(portfolio)


@router.delete("/{portfolio_id}", status_code=204, summary="Delete a portfolio")
async def delete_portfolio(
    portfolio_id: str,
    current_user: UserIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == current_user.id)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(404, detail="Portfolio not found")
    await db.delete(portfolio)
    await db.commit()


# =============================================================
# HOLDINGS (POSITIONS + TRANSACTIONS)
# =============================================================

@router.post("/{portfolio_id}/holdings", response_model=HoldingResponse, status_code=201,
             summary="Add a holding (record a buy/sell)")
async def add_holding(
    portfolio_id: str,
    body: HoldingCreate,
    current_user: UserIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HoldingResponse:
    """
    Record a BUY or SELL transaction and update the position.
    BUY increases position, SELL decreases it.
    """
    # Verify portfolio ownership
    port_result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == current_user.id)
    )
    portfolio = port_result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(404, detail="Portfolio not found")

    # Resolve asset
    asset = await _resolve_or_create_asset(body.ticker, db)

    # Record transaction
    tx = TransactionLedger(
        user_id=current_user.id,
        portfolio_id=portfolio_id,
        asset_id=asset.asset_id,
        action_type=body.action,
        quantity=body.quantity,
        execution_price=body.price,
        settlement_currency="USD",
        executed_at=datetime.utcnow(),
    )
    db.add(tx)

    # Find or create current position
    pos_result = await db.execute(
        select(PositionJournal).where(and_(
            PositionJournal.user_id == current_user.id,
            PositionJournal.portfolio_id == portfolio_id,
            PositionJournal.asset_id == asset.asset_id,
            PositionJournal.is_current == True,
        ))
    )
    position = pos_result.scalar_one_or_none()

    if body.action == "BUY":
        if position:
            # Update average cost and quantity
            old_total = position.net_quantity * position.average_cost
            new_total = body.quantity * body.price
            new_qty = position.net_quantity + body.quantity
            position.average_cost = (old_total + new_total) / new_qty if new_qty > 0 else 0
            position.net_quantity = new_qty
        else:
            # Create new position
            position = PositionJournal(
                user_id=current_user.id,
                portfolio_id=portfolio_id,
                asset_id=asset.asset_id,
                net_quantity=body.quantity,
                average_cost=body.price,
                position_currency="USD",
                is_current=True,
            )
            db.add(position)
    elif body.action == "SELL":
        if not position or position.net_quantity < body.quantity:
            raise HTTPException(400, detail="Insufficient holdings to sell")
        
        # Record realized P&L
        realized = (body.price - position.average_cost) * body.quantity
        position.realized_pnl = (position.realized_pnl or 0) + realized
        position.net_quantity -= body.quantity
        
        # Close position if fully sold
        if position.net_quantity <= 0.001:
            position.net_quantity = 0
            position.is_current = False
            position.valid_to = datetime.utcnow()

    await db.commit()
    if position and position.id:
        await db.refresh(position)

    total_cost = (position.net_quantity * position.average_cost) if position else 0

    return HoldingResponse(
        position_id=position.id if position else "",
        ticker=body.ticker,
        quantity=position.net_quantity if position else 0,
        avg_cost=position.average_cost if position else 0,
        total_cost=round(total_cost, 2),
    )


@router.get("/{portfolio_id}/holdings", response_model=List[HoldingResponse],
            summary="List current holdings with live P&L")
async def list_holdings(
    portfolio_id: str,
    current_user: UserIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[HoldingResponse]:
    """Get all open positions in a portfolio with live prices."""
    # Verify ownership
    port_result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == current_user.id)
    )
    if not port_result.scalar_one_or_none():
        raise HTTPException(404, detail="Portfolio not found")

    # Fetch positions with asset info
    result = await db.execute(
        select(PositionJournal, AssetMaster.ticker_symbol)
        .join(AssetMaster, PositionJournal.asset_id == AssetMaster.asset_id)
        .where(and_(
            PositionJournal.portfolio_id == portfolio_id,
            PositionJournal.user_id == current_user.id,
            PositionJournal.is_current == True,
            PositionJournal.net_quantity > 0,
        ))
    )

    holdings = []
    for pos, ticker in result.all():
        total_cost = pos.net_quantity * pos.average_cost

        # Fetch live price
        current_price = None
        current_value = None
        unrealized_pnl = None
        pnl_pct = None

        try:
            from src.ingestion.yf_client_v2 import fetch_market_snapshot
            snapshot = await fetch_market_snapshot(ticker)
            if snapshot and snapshot.current_price:
                current_price = snapshot.current_price
                current_value = pos.net_quantity * current_price
                unrealized_pnl = current_value - total_cost
                pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0
        except Exception as e:
            logger.warning(f"Failed to fetch price for {ticker}: {e}")

        holdings.append(HoldingResponse(
            position_id=pos.id,
            ticker=ticker,
            quantity=pos.net_quantity,
            avg_cost=round(pos.average_cost, 4),
            total_cost=round(total_cost, 2),
            current_price=round(current_price, 4) if current_price else None,
            current_value=round(current_value, 2) if current_value else None,
            unrealized_pnl=round(unrealized_pnl, 2) if unrealized_pnl is not None else None,
            pnl_pct=round(pnl_pct, 2) if pnl_pct is not None else None,
        ))

    return holdings


@router.get("/{portfolio_id}/summary", response_model=PortfolioSummary,
            summary="Full portfolio summary with live values")
async def portfolio_summary(
    portfolio_id: str,
    current_user: UserIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioSummary:
    """Get portfolio details with all holdings and aggregate P&L."""
    port_result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == current_user.id)
    )
    portfolio = port_result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(404, detail="Portfolio not found")

    holdings = await list_holdings(portfolio_id, current_user, db)

    total_invested = sum(h.total_cost for h in holdings)
    total_current = sum(h.current_value for h in holdings if h.current_value is not None)
    has_prices = any(h.current_value is not None for h in holdings)
    total_pnl = (total_current - total_invested) if has_prices else None
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 and total_pnl is not None else None

    return PortfolioSummary(
        portfolio=PortfolioResponse.model_validate(portfolio),
        total_invested=round(total_invested, 2),
        total_current_value=round(total_current, 2) if has_prices else None,
        total_pnl=round(total_pnl, 2) if total_pnl is not None else None,
        total_pnl_pct=round(total_pnl_pct, 2) if total_pnl_pct is not None else None,
        holdings=holdings,
    )


@router.delete("/{portfolio_id}/holdings/{position_id}", status_code=204,
               summary="Remove a position (close it)")
async def close_position(
    portfolio_id: str,
    position_id: str,
    current_user: UserIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(PositionJournal).where(and_(
            PositionJournal.id == position_id,
            PositionJournal.portfolio_id == portfolio_id,
            PositionJournal.user_id == current_user.id,
            PositionJournal.is_current == True,
        ))
    )
    position = result.scalar_one_or_none()
    if not position:
        raise HTTPException(404, detail="Position not found")

    position.is_current = False
    position.valid_to = datetime.utcnow()
    position.net_quantity = 0
    await db.commit()


# =============================================================
# WATCHLIST
# =============================================================

async def _resolve_asset(ticker: str, db: AsyncSession) -> AssetMaster | None:
    result = await db.execute(
        select(AssetMaster).where(AssetMaster.ticker_symbol == ticker.upper()).limit(1)
    )
    return result.scalar_one_or_none()


@router.post("/watchlist", response_model=WatchlistResponse, status_code=201,
             summary="Add asset to watchlist")
async def add_to_watchlist(
    body: WatchlistCreate,
    current_user: UserIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchlistResponse:
    # Auto-create asset if needed (removes the friction)
    asset = await _resolve_asset(body.ticker, db)
    if not asset:
        asset = await _resolve_or_create_asset(body.ticker, db)

    # Check duplicate
    existing = await db.execute(
        select(Watchlist).where(
            Watchlist.user_id == current_user.id,
            Watchlist.asset_id == asset.asset_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, detail=f"{body.ticker} is already on your watchlist")

    item = Watchlist(
        user_id=current_user.id,
        asset_id=asset.asset_id,
        portfolio_id=body.portfolio_id,
        price_trigger_high=body.price_trigger_high,
        price_trigger_low=body.price_trigger_low,
        sentiment_trigger_high=body.sentiment_trigger_high,
        sentiment_trigger_low=body.sentiment_trigger_low,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    logger.info(f"{current_user.email} added {body.ticker} to watchlist")

    return WatchlistResponse(
        id=item.id, user_id=item.user_id, ticker=asset.ticker_symbol,
        portfolio_id=item.portfolio_id,
        price_trigger_high=item.price_trigger_high,
        price_trigger_low=item.price_trigger_low,
        sentiment_trigger_high=item.sentiment_trigger_high,
        sentiment_trigger_low=item.sentiment_trigger_low,
    )


@router.get("/watchlist", response_model=List[WatchlistResponse], summary="List watchlist")
async def list_watchlist(
    current_user: UserIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[WatchlistResponse]:
    result = await db.execute(
        select(Watchlist, AssetMaster.ticker_symbol)
        .join(AssetMaster, Watchlist.asset_id == AssetMaster.asset_id)
        .where(Watchlist.user_id == current_user.id)
    )
    return [
        WatchlistResponse(
            id=w.id, user_id=w.user_id, ticker=ticker,
            portfolio_id=w.portfolio_id,
            price_trigger_high=w.price_trigger_high,
            price_trigger_low=w.price_trigger_low,
            sentiment_trigger_high=w.sentiment_trigger_high,
            sentiment_trigger_low=w.sentiment_trigger_low,
        )
        for w, ticker in result.all()
    ]


@router.delete("/watchlist/{watchlist_id}", status_code=204, summary="Remove from watchlist")
async def remove_from_watchlist(
    watchlist_id: str,
    current_user: UserIdentity = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.user_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, detail="Watchlist item not found")
    await db.delete(item)
    await db.commit()
