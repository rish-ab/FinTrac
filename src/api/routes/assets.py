# =============================================================
# src/api/routes/assets.py
#
# Asset discovery endpoints for multi-asset support
#
# V3 Phase 8: Added /search endpoint for autocomplete,
# /registry for full asset listing, expanded /examples.
# =============================================================

from fastapi import APIRouter, Query
from typing import Dict, List

from src.ingestion.asset_registry import (
    get_all_asset_symbols, search_assets, AssetClass,
    FOREX_PAIRS, BONDS, COMMODITIES, CRYPTO, INDICES,
)

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/search")
async def search_ticker(
    q: str = Query(..., min_length=1, max_length=20, description="Search query"),
    limit: int = Query(default=15, ge=1, le=50),
) -> List[Dict]:
    """
    Search across all asset registries by ticker or name.
    Supports partial matching: 'INR' finds USDINR, EURINR, etc.
    'gold' finds Gold Futures. 'bit' finds Bitcoin.
    
    For tickers not in the registry, the frontend can still submit
    them directly — yfinance will validate at analysis time.
    """
    return search_assets(q, limit)


@router.get("/registry")
async def get_full_registry() -> Dict[str, List[Dict]]:
    """
    Return the full asset registry grouped by class.
    Each entry has ticker, name, yf_symbol.
    """
    def _format_registry(registry: dict, asset_class: str) -> List[Dict]:
        return [
            {
                "ticker": ticker,
                "name": meta.get("name", ticker),
                "asset_class": asset_class,
            }
            for ticker, meta in registry.items()
        ]
    
    return {
        "equities": [
            {"ticker": "AAPL",  "name": "Apple Inc.",           "asset_class": "EQUITY"},
            {"ticker": "MSFT",  "name": "Microsoft Corp.",      "asset_class": "EQUITY"},
            {"ticker": "GOOGL", "name": "Alphabet Inc.",        "asset_class": "EQUITY"},
            {"ticker": "AMZN",  "name": "Amazon.com Inc.",      "asset_class": "EQUITY"},
            {"ticker": "TSLA",  "name": "Tesla Inc.",           "asset_class": "EQUITY"},
            {"ticker": "NVDA",  "name": "NVIDIA Corp.",         "asset_class": "EQUITY"},
            {"ticker": "META",  "name": "Meta Platforms",       "asset_class": "EQUITY"},
            {"ticker": "JPM",   "name": "JPMorgan Chase",       "asset_class": "EQUITY"},
            {"ticker": "V",     "name": "Visa Inc.",            "asset_class": "EQUITY"},
            {"ticker": "JNJ",   "name": "Johnson & Johnson",   "asset_class": "EQUITY"},
            {"ticker": "XOM",   "name": "Exxon Mobil Corp.",    "asset_class": "EQUITY"},
            {"ticker": "WMT",   "name": "Walmart Inc.",         "asset_class": "EQUITY"},
            {"ticker": "PG",    "name": "Procter & Gamble",     "asset_class": "EQUITY"},
            {"ticker": "UNH",   "name": "UnitedHealth Group",   "asset_class": "EQUITY"},
            {"ticker": "HD",    "name": "Home Depot",           "asset_class": "EQUITY"},
            {"ticker": "RELIANCE.NS", "name": "Reliance Industries (India)", "asset_class": "EQUITY"},
            {"ticker": "TCS.NS",     "name": "TCS (India)",     "asset_class": "EQUITY"},
            {"ticker": "INFY.NS",    "name": "Infosys (India)", "asset_class": "EQUITY"},
        ],
        "forex": _format_registry(FOREX_PAIRS, "FOREX"),
        "bonds": _format_registry(BONDS, "BOND"),
        "commodities": _format_registry(COMMODITIES, "COMMODITY"),
        "crypto": _format_registry(CRYPTO, "CRYPTO"),
        "indices": _format_registry(INDICES, "INDEX"),
    }


@router.get("/list")
async def list_assets() -> Dict[str, List[str]]:
    """Get all available asset tickers grouped by class."""
    assets = get_all_asset_symbols()
    return {
        "forex": assets[AssetClass.FOREX],
        "bonds": assets[AssetClass.BOND],
        "commodities": assets[AssetClass.COMMODITY],
        "crypto": assets[AssetClass.CRYPTO],
        "indices": assets.get(AssetClass.INDEX, []),
    }


@router.get("/examples")
async def get_example_tickers() -> Dict[str, List[Dict[str, str]]]:
    """Get example tickers for each asset class with descriptions."""
    return {
        "equities": [
            {"ticker": "AAPL", "name": "Apple Inc."},
            {"ticker": "TSLA", "name": "Tesla Inc."},
            {"ticker": "JPM",  "name": "JPMorgan Chase"},
            {"ticker": "NVDA", "name": "NVIDIA Corp."},
            {"ticker": "MSFT", "name": "Microsoft Corp."},
            {"ticker": "RELIANCE.NS", "name": "Reliance Industries"},
        ],
        "forex": [
            {"ticker": "EURUSD", "name": "Euro / US Dollar"},
            {"ticker": "GBPUSD", "name": "British Pound / US Dollar"},
            {"ticker": "USDJPY", "name": "US Dollar / Japanese Yen"},
            {"ticker": "USDINR", "name": "US Dollar / Indian Rupee"},
            {"ticker": "USDCNY", "name": "US Dollar / Chinese Yuan"},
        ],
        "bonds": [
            {"ticker": "TNX", "name": "US Treasury 10-Year Yield"},
            {"ticker": "TYX", "name": "US Treasury 30-Year Yield"},
            {"ticker": "FVX", "name": "US Treasury 5-Year Yield"},
        ],
        "commodities": [
            {"ticker": "GOLD",   "name": "Gold Futures"},
            {"ticker": "OIL",    "name": "Crude Oil WTI Futures"},
            {"ticker": "SILVER", "name": "Silver Futures"},
            {"ticker": "NATGAS", "name": "Natural Gas Futures"},
            {"ticker": "COPPER", "name": "Copper Futures"},
        ],
        "crypto": [
            {"ticker": "BTC",  "name": "Bitcoin"},
            {"ticker": "ETH",  "name": "Ethereum"},
            {"ticker": "SOL",  "name": "Solana"},
            {"ticker": "XRP",  "name": "Ripple"},
        ],
        "indices": [
            {"ticker": "SPX",    "name": "S&P 500"},
            {"ticker": "NASDAQ", "name": "NASDAQ Composite"},
            {"ticker": "NIFTY",  "name": "Nifty 50 (India)"},
            {"ticker": "SENSEX", "name": "BSE Sensex (India)"},
        ],
    }
