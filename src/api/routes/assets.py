# =============================================================
# src/api/routes/assets.py
#
# Asset discovery endpoints for multi-asset support
# =============================================================

from fastapi import APIRouter
from typing import Dict, List

from src.ingestion.asset_registry import get_all_asset_symbols, AssetClass

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/list")
async def list_assets() -> Dict[str, List[str]]:
    """
    Get all available assets grouped by class.
    Frontend uses this to populate dropdowns.
    """
    assets = get_all_asset_symbols()
    
    return {
        "forex": assets[AssetClass.FOREX],
        "bonds": assets[AssetClass.BOND],
        "commodities": assets[AssetClass.COMMODITY],
        "crypto": assets[AssetClass.CRYPTO],
    }


@router.get("/examples")
async def get_example_tickers() -> Dict[str, List[Dict[str, str]]]:
    """
    Get example tickers for each asset class with descriptions.
    """
    return {
        "equities": [
            {"ticker": "AAPL", "name": "Apple Inc."},
            {"ticker": "TSLA", "name": "Tesla Inc."},
            {"ticker": "JPM", "name": "JPMorgan Chase"},
        ],
        "forex": [
            {"ticker": "EURUSD", "name": "Euro / US Dollar"},
            {"ticker": "GBPUSD", "name": "British Pound / US Dollar"},
            {"ticker": "USDJPY", "name": "US Dollar / Japanese Yen"},
        ],
        "bonds": [
            {"ticker": "TNX", "name": "US Treasury 10-Year Yield"},
            {"ticker": "TYX", "name": "US Treasury 30-Year Yield"},
        ],
        "commodities": [
            {"ticker": "GOLD", "name": "Gold Futures"},
            {"ticker": "OIL", "name": "Crude Oil WTI Futures"},
            {"ticker": "SILVER", "name": "Silver Futures"},
        ],
        "crypto": [
            {"ticker": "BTC", "name": "Bitcoin"},
            {"ticker": "ETH", "name": "Ethereum"},
        ],
    }
