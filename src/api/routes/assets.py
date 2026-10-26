# =============================================================
# src/api/routes/assets.py
#
# Asset discovery endpoints for multi-asset support.
#
# SEARCH ARCHITECTURE:
# Two sources feed /assets/search and are merged:
#
#   1. Local registry (asset_registry.py) — curated forex pairs,
#      bonds, commodities, crypto and indices. These need a
#      hardcoded mapping because their yfinance symbols are not
#      guessable (GOLD -> GC=F, NIFTY -> ^NSEI, USDINR -> USDINR=X).
#
#   2. Yahoo Finance search (equity_search.py) — the full equity,
#      ETF and fund universe. Cannot be hardcoded (~50k symbols)
#      and needs no mapping, since the ticker IS the yf symbol.
#
# Registry hits rank above Yahoo hits so that typing "GOLD"
# surfaces the curated futures contract rather than an unrelated
# small-cap named "Gold Corp".
# =============================================================

from typing import Dict, List

from fastapi import APIRouter, Query

from src.ingestion.asset_registry import (
    get_all_asset_symbols, search_assets, AssetClass,
    FOREX_PAIRS, BONDS, COMMODITIES, CRYPTO, INDICES,
)
from src.ingestion.equity_search import search_equities

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/search")
async def search_ticker(
    q: str = Query(..., min_length=1, max_length=40, description="Ticker or company name"),
    limit: int = Query(default=15, ge=1, le=50),
) -> List[Dict]:
    """
    Unified search across curated registries and the full Yahoo universe.

    Examples:
      'paypal' -> PYPL (Yahoo equity search)
      'PYPL'   -> PYPL
      'INR'    -> USDINR, EURINR, GBPINR, JPYINR (registry)
      'gold'   -> GOLD futures (registry), then gold-related equities/ETFs
      'nifty'  -> NIFTY index (registry)
    """
    query = q.strip()

    # 1. Curated registry — non-guessable symbol mappings
    registry_results = search_assets(query, limit=limit)

    # 2. Yahoo — equities, ETFs, funds. Never let an upstream failure
    #    break the endpoint; search_equities returns [] on error.
    remaining = max(limit - len(registry_results), 5)
    equity_results = await search_equities(query, limit=remaining)

    # 3. Merge, de-duplicating on the resolved yfinance symbol so a
    #    registry entry and its Yahoo equivalent don't both appear.
    seen_symbols = {r["yf_symbol"].upper() for r in registry_results}
    seen_tickers = {r["ticker"].upper() for r in registry_results}

    merged = list(registry_results)
    for result in equity_results:
        symbol = result["yf_symbol"].upper()
        if symbol in seen_symbols or symbol in seen_tickers:
            continue
        seen_symbols.add(symbol)
        merged.append(result)

    return merged[:limit]


@router.get("/registry")
async def get_full_registry() -> Dict[str, List[Dict]]:
    """Full curated registry grouped by asset class, plus example equities."""
    def _format(registry: dict, asset_class: str) -> List[Dict]:
        return [
            {"ticker": t, "name": m.get("name", t), "asset_class": asset_class}
            for t, m in registry.items()
        ]

    return {
        "equities": [
            {"ticker": "AAPL",  "name": "Apple Inc.",         "asset_class": "EQUITY"},
            {"ticker": "MSFT",  "name": "Microsoft Corp.",    "asset_class": "EQUITY"},
            {"ticker": "GOOGL", "name": "Alphabet Inc.",      "asset_class": "EQUITY"},
            {"ticker": "AMZN",  "name": "Amazon.com Inc.",    "asset_class": "EQUITY"},
            {"ticker": "TSLA",  "name": "Tesla Inc.",         "asset_class": "EQUITY"},
            {"ticker": "NVDA",  "name": "NVIDIA Corp.",       "asset_class": "EQUITY"},
            {"ticker": "META",  "name": "Meta Platforms",     "asset_class": "EQUITY"},
            {"ticker": "JPM",   "name": "JPMorgan Chase",     "asset_class": "EQUITY"},
            {"ticker": "V",     "name": "Visa Inc.",          "asset_class": "EQUITY"},
            {"ticker": "PYPL",  "name": "PayPal Holdings",    "asset_class": "EQUITY"},
            {"ticker": "XOM",   "name": "Exxon Mobil Corp.",  "asset_class": "EQUITY"},
            {"ticker": "WMT",   "name": "Walmart Inc.",       "asset_class": "EQUITY"},
            {"ticker": "RELIANCE.NS", "name": "Reliance Industries (India)", "asset_class": "EQUITY"},
            {"ticker": "TCS.NS",      "name": "TCS (India)",   "asset_class": "EQUITY"},
            {"ticker": "INFY.NS",     "name": "Infosys (India)", "asset_class": "EQUITY"},
        ],
        "forex":       _format(FOREX_PAIRS, "FOREX"),
        "bonds":       _format(BONDS, "BOND"),
        "commodities": _format(COMMODITIES, "COMMODITY"),
        "crypto":      _format(CRYPTO, "CRYPTO"),
        "indices":     _format(INDICES, "INDEX"),
    }


@router.get("/list")
async def list_assets() -> Dict[str, List[str]]:
    """All curated registry tickers grouped by class."""
    assets = get_all_asset_symbols()
    return {
        "forex":       assets[AssetClass.FOREX],
        "bonds":       assets[AssetClass.BOND],
        "commodities": assets[AssetClass.COMMODITY],
        "crypto":      assets[AssetClass.CRYPTO],
        "indices":     assets.get(AssetClass.INDEX, []),
    }


@router.get("/examples")
async def get_example_tickers() -> Dict[str, List[Dict[str, str]]]:
    """Example tickers per asset class, used by the browse tabs in the UI."""
    return {
        "equities": [
            {"ticker": "AAPL", "name": "Apple Inc."},
            {"ticker": "TSLA", "name": "Tesla Inc."},
            {"ticker": "JPM",  "name": "JPMorgan Chase"},
            {"ticker": "NVDA", "name": "NVIDIA Corp."},
            {"ticker": "MSFT", "name": "Microsoft Corp."},
            {"ticker": "PYPL", "name": "PayPal Holdings"},
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
            {"ticker": "BTC", "name": "Bitcoin"},
            {"ticker": "ETH", "name": "Ethereum"},
            {"ticker": "SOL", "name": "Solana"},
            {"ticker": "XRP", "name": "Ripple"},
        ],
        "indices": [
            {"ticker": "SPX",    "name": "S&P 500"},
            {"ticker": "NASDAQ", "name": "NASDAQ Composite"},
            {"ticker": "NIFTY",  "name": "Nifty 50 (India)"},
            {"ticker": "SENSEX", "name": "BSE Sensex (India)"},
        ],
    }
