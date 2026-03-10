# =============================================================
# src/db/asset_seeder.py
#
# Auto-creates AssetMaster rows from yfinance market snapshots.
# Called from the evaluate route after a successful data fetch.
#
# WHY NOT SEED MANUALLY?
# We already have all the data we need from yfinance — sector,
# industry, exchange, currency. Rather than maintaining a
# separate seed script, we upsert the AssetMaster row on every
# evaluate query. Idempotent — safe to call many times.
# =============================================================

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AssetMaster
from src.api.schemas.investment import MarketSnapshot


async def ensure_asset_exists(
    snapshot: MarketSnapshot,
    db:       AsyncSession,
) -> str:
    """
    Upsert an AssetMaster row from a yfinance snapshot.
    Returns the asset_id.
    Creates the row if it doesn't exist, updates fields if it does.
    """
    ticker = snapshot.ticker.upper()

    result = await db.execute(
        select(AssetMaster)
        .where(AssetMaster.ticker_symbol == ticker)
        .limit(1)
    )
    asset = result.scalar_one_or_none()

    if asset:
        # Update fields in case they've changed
        asset.sector   = snapshot.sector   or asset.sector
        asset.industry = snapshot.industry or asset.industry
        await db.commit()
        return asset.asset_id

    # Create new row
    asset = AssetMaster(
        ticker_symbol         = ticker,
        exchange              = "UNKNOWN",
        denomination_currency = snapshot.currency or "USD",
        sector                = snapshot.sector,
        industry              = snapshot.industry,
        country_code          = "US",
        status                = "ACTIVE",
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    logger.info(f"AssetMaster row created for {ticker} (id: {asset.asset_id[:8]}...)")
    return asset.asset_id