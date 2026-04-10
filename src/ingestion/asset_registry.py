# =============================================================
# src/ingestion/asset_registry.py
#
# Multi-asset class support configuration
# Maps user-friendly tickers to yfinance symbols and metadata
# =============================================================

from enum import Enum
from typing import Dict, Optional, Tuple


class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    FOREX = "FOREX"
    BOND = "BOND"
    COMMODITY = "COMMODITY"
    CRYPTO = "CRYPTO"


# ── FOREX PAIRS ────────────────────────────────────────────────────────────────
# yfinance format: EURUSD=X, GBPUSD=X, etc.
# User can type: EUR/USD, EURUSD, EUR-USD (we normalize)

FOREX_PAIRS = {
    # Major pairs
    "EURUSD": {"symbol": "EURUSD=X", "name": "Euro / US Dollar", "base": "EUR", "quote": "USD"},
    "GBPUSD": {"symbol": "GBPUSD=X", "name": "British Pound / US Dollar", "base": "GBP", "quote": "USD"},
    "USDJPY": {"symbol": "USDJPY=X", "name": "US Dollar / Japanese Yen", "base": "USD", "quote": "JPY"},
    "USDCHF": {"symbol": "USDCHF=X", "name": "US Dollar / Swiss Franc", "base": "USD", "quote": "CHF"},
    "AUDUSD": {"symbol": "AUDUSD=X", "name": "Australian Dollar / US Dollar", "base": "AUD", "quote": "USD"},
    "USDCAD": {"symbol": "USDCAD=X", "name": "US Dollar / Canadian Dollar", "base": "USD", "quote": "CAD"},
    "NZDUSD": {"symbol": "NZDUSD=X", "name": "New Zealand Dollar / US Dollar", "base": "NZD", "quote": "USD"},
    
    # Cross pairs
    "EURGBP": {"symbol": "EURGBP=X", "name": "Euro / British Pound", "base": "EUR", "quote": "GBP"},
    "EURJPY": {"symbol": "EURJPY=X", "name": "Euro / Japanese Yen", "base": "EUR", "quote": "JPY"},
    "GBPJPY": {"symbol": "GBPJPY=X", "name": "British Pound / Japanese Yen", "base": "GBP", "quote": "JPY"},
}


# ── BONDS ──────────────────────────────────────────────────────────────────────
# yfinance symbols for treasury yields
# Note: These are yield RATES, not bond prices

BONDS = {
    "TNX": {"symbol": "^TNX", "name": "US Treasury 10-Year Yield", "maturity": "10Y", "country": "US"},
    "TYX": {"symbol": "^TYX", "name": "US Treasury 30-Year Yield", "maturity": "30Y", "country": "US"},
    "FVX": {"symbol": "^FVX", "name": "US Treasury 5-Year Yield", "maturity": "5Y", "country": "US"},
    "IRX": {"symbol": "^IRX", "name": "US Treasury 13-Week Yield", "maturity": "3M", "country": "US"},
}


# ── COMMODITIES ────────────────────────────────────────────────────────────────
# yfinance futures symbols

COMMODITIES = {
    "GOLD": {"symbol": "GC=F", "name": "Gold Futures", "unit": "USD/oz", "sector": "Precious Metals"},
    "SILVER": {"symbol": "SI=F", "name": "Silver Futures", "unit": "USD/oz", "sector": "Precious Metals"},
    "OIL": {"symbol": "CL=F", "name": "Crude Oil WTI Futures", "unit": "USD/barrel", "sector": "Energy"},
    "BRENT": {"symbol": "BZ=F", "name": "Brent Crude Oil Futures", "unit": "USD/barrel", "sector": "Energy"},
    "NATGAS": {"symbol": "NG=F", "name": "Natural Gas Futures", "unit": "USD/MMBtu", "sector": "Energy"},
    "COPPER": {"symbol": "HG=F", "name": "Copper Futures", "unit": "USD/lb", "sector": "Industrial Metals"},
    "WHEAT": {"symbol": "ZW=F", "name": "Wheat Futures", "unit": "USD/bushel", "sector": "Agriculture"},
    "CORN": {"symbol": "ZC=F", "name": "Corn Futures", "unit": "USD/bushel", "sector": "Agriculture"},
}


# ── CRYPTO ─────────────────────────────────────────────────────────────────────
# yfinance format: BTC-USD, ETH-USD

CRYPTO = {
    "BTC": {"symbol": "BTC-USD", "name": "Bitcoin"},
    "ETH": {"symbol": "ETH-USD", "name": "Ethereum"},
    "USDT": {"symbol": "USDT-USD", "name": "Tether"},
    "BNB": {"symbol": "BNB-USD", "name": "Binance Coin"},
    "SOL": {"symbol": "SOL-USD", "name": "Solana"},
}


# ── TICKER RESOLUTION ──────────────────────────────────────────────────────────

def normalize_ticker(ticker: str) -> str:
    """
    Normalize user input to a consistent format.
    EUR/USD, EUR-USD, EURUSD → EURUSD
    """
    return ticker.upper().replace("/", "").replace("-", "").strip()


def resolve_ticker(user_input: str) -> Tuple[str, AssetClass, Dict]:
    """
    Resolve user input to (yfinance_symbol, asset_class, metadata).
    
    Examples:
        "AAPL" → ("AAPL", EQUITY, {})
        "EUR/USD" → ("EURUSD=X", FOREX, {...})
        "GOLD" → ("GC=F", COMMODITY, {...})
        "TNX" → ("^TNX", BOND, {...})
        "BTC" → ("BTC-USD", CRYPTO, {...})
    
    Returns:
        (yfinance_symbol, asset_class, metadata_dict)
    
    Raises:
        ValueError if ticker not recognized
    """
    normalized = normalize_ticker(user_input)
    
    # Check FOREX
    if normalized in FOREX_PAIRS:
        meta = FOREX_PAIRS[normalized]
        return meta["symbol"], AssetClass.FOREX, meta
    
    # Check BONDS
    if normalized in BONDS:
        meta = BONDS[normalized]
        return meta["symbol"], AssetClass.BOND, meta
    
    # Check COMMODITIES
    if normalized in COMMODITIES:
        meta = COMMODITIES[normalized]
        return meta["symbol"], AssetClass.COMMODITY, meta
    
    # Check CRYPTO
    if normalized in CRYPTO:
        meta = CRYPTO[normalized]
        return meta["symbol"], AssetClass.CRYPTO, meta
    
    # Default to EQUITY (stock ticker)
    # User typed something like AAPL, TSLA, etc.
    return user_input.upper(), AssetClass.EQUITY, {}


def get_asset_display_name(ticker: str, asset_class: AssetClass, metadata: Dict) -> str:
    """
    Get a human-readable name for display.
    """
    if asset_class == AssetClass.FOREX:
        return f"{metadata.get('base')}/{metadata.get('quote')}"
    elif asset_class in [AssetClass.BOND, AssetClass.COMMODITY, AssetClass.CRYPTO]:
        return metadata.get("name", ticker)
    else:
        return ticker  # For equities, company name comes from yfinance


# ── ASSET-SPECIFIC PROJECTION PARAMETERS ──────────────────────────────────────

def get_projection_params(asset_class: AssetClass) -> Dict:
    """
    Return asset-specific parameters for budget projections.
    Different asset classes have different risk/return profiles.
    """
    params = {
        AssetClass.EQUITY: {
            "low_multiplier": 0.5,    # Bear case: -50%
            "high_multiplier": 2.0,   # Bull case: +100%
            "default_horizon": 5,
        },
        AssetClass.FOREX: {
            "low_multiplier": 0.90,   # FOREX moves are smaller
            "high_multiplier": 1.10,
            "default_horizon": 1,     # Shorter horizons for FX
        },
        AssetClass.BOND: {
            "low_multiplier": 0.95,   # Bonds are stable
            "high_multiplier": 1.08,
            "default_horizon": 3,
        },
        AssetClass.COMMODITY: {
            "low_multiplier": 0.60,   # Commodities volatile
            "high_multiplier": 1.80,
            "default_horizon": 2,
        },
        AssetClass.CRYPTO: {
            "low_multiplier": 0.20,   # Crypto: extreme volatility
            "high_multiplier": 5.0,
            "default_horizon": 1,
        },
    }
    return params.get(asset_class, params[AssetClass.EQUITY])


# ── VALIDATION ─────────────────────────────────────────────────────────────────

def is_valid_ticker(ticker: str) -> bool:
    """
    Check if a ticker is recognized (returns True for equities by default).
    """
    normalized = normalize_ticker(ticker)
    
    # Check all registries
    if normalized in FOREX_PAIRS:
        return True
    if normalized in BONDS:
        return True
    if normalized in COMMODITIES:
        return True
    if normalized in CRYPTO:
        return True
    
    # For equities, we can't pre-validate (thousands of tickers exist)
    # yfinance will validate when we fetch data
    return True  # Assume valid, let yfinance reject if wrong


# ── HELPER: LIST ALL ASSETS ────────────────────────────────────────────────────

def get_all_asset_symbols() -> Dict[AssetClass, list]:
    """
    Return all available assets grouped by class.
    Useful for frontend dropdown population.
    """
    return {
        AssetClass.FOREX: list(FOREX_PAIRS.keys()),
        AssetClass.BOND: list(BONDS.keys()),
        AssetClass.COMMODITY: list(COMMODITIES.keys()),
        AssetClass.CRYPTO: list(CRYPTO.keys()),
    }
