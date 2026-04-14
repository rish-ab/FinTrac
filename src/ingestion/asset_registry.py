# =============================================================
# src/ingestion/asset_registry.py
#
# Multi-asset class support configuration.
# Maps user-friendly tickers to yfinance symbols and metadata.
#
# V3 Phase 8: Expanded to 70+ predefined assets with search
# support. The system is also open-ended — any yfinance-valid
# ticker can be entered directly via the custom input.
# =============================================================

from enum import Enum
from typing import Dict, List, Optional, Tuple


class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    FOREX = "FOREX"
    BOND = "BOND"
    COMMODITY = "COMMODITY"
    CRYPTO = "CRYPTO"
    INDEX = "INDEX"


# ── FOREX PAIRS ────────────────────────────────────────────────────────────────

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
    "EURCHF": {"symbol": "EURCHF=X", "name": "Euro / Swiss Franc", "base": "EUR", "quote": "CHF"},
    "AUDNZD": {"symbol": "AUDNZD=X", "name": "Australian Dollar / New Zealand Dollar", "base": "AUD", "quote": "NZD"},
    "AUDJPY": {"symbol": "AUDJPY=X", "name": "Australian Dollar / Japanese Yen", "base": "AUD", "quote": "JPY"},
    "CADJPY": {"symbol": "CADJPY=X", "name": "Canadian Dollar / Japanese Yen", "base": "CAD", "quote": "JPY"},
    
    # Emerging market pairs — INR
    "USDINR": {"symbol": "USDINR=X", "name": "US Dollar / Indian Rupee", "base": "USD", "quote": "INR"},
    "INRUSD": {"symbol": "INR=X",    "name": "Indian Rupee / US Dollar", "base": "INR", "quote": "USD"},
    "EURINR": {"symbol": "EURINR=X", "name": "Euro / Indian Rupee", "base": "EUR", "quote": "INR"},
    "GBPINR": {"symbol": "GBPINR=X", "name": "British Pound / Indian Rupee", "base": "GBP", "quote": "INR"},
    "JPYINR": {"symbol": "JPYINR=X", "name": "Japanese Yen / Indian Rupee", "base": "JPY", "quote": "INR"},
    
    # Emerging market — Brazil, China, South Africa, Mexico, Turkey, Korea, Singapore
    "USDBRL": {"symbol": "USDBRL=X", "name": "US Dollar / Brazilian Real", "base": "USD", "quote": "BRL"},
    "USDCNY": {"symbol": "USDCNY=X", "name": "US Dollar / Chinese Yuan", "base": "USD", "quote": "CNY"},
    "USDZAR": {"symbol": "USDZAR=X", "name": "US Dollar / South African Rand", "base": "USD", "quote": "ZAR"},
    "USDMXN": {"symbol": "USDMXN=X", "name": "US Dollar / Mexican Peso", "base": "USD", "quote": "MXN"},
    "USDTRY": {"symbol": "USDTRY=X", "name": "US Dollar / Turkish Lira", "base": "USD", "quote": "TRY"},
    "USDKRW": {"symbol": "USDKRW=X", "name": "US Dollar / South Korean Won", "base": "USD", "quote": "KRW"},
    "USDSGD": {"symbol": "USDSGD=X", "name": "US Dollar / Singapore Dollar", "base": "USD", "quote": "SGD"},
    "USDRUB": {"symbol": "USDRUB=X", "name": "US Dollar / Russian Ruble", "base": "USD", "quote": "RUB"},
    "USDTHB": {"symbol": "USDTHB=X", "name": "US Dollar / Thai Baht", "base": "USD", "quote": "THB"},
    "USDPLN": {"symbol": "USDPLN=X", "name": "US Dollar / Polish Zloty", "base": "USD", "quote": "PLN"},
    "USDSEK": {"symbol": "USDSEK=X", "name": "US Dollar / Swedish Krona", "base": "USD", "quote": "SEK"},
    "USDNOK": {"symbol": "USDNOK=X", "name": "US Dollar / Norwegian Krone", "base": "USD", "quote": "NOK"},
    "USDHKD": {"symbol": "USDHKD=X", "name": "US Dollar / Hong Kong Dollar", "base": "USD", "quote": "HKD"},
    "USDAED": {"symbol": "USDAED=X", "name": "US Dollar / UAE Dirham", "base": "USD", "quote": "AED"},
    "USDSAR": {"symbol": "USDSAR=X", "name": "US Dollar / Saudi Riyal", "base": "USD", "quote": "SAR"},
}


# ── BONDS ──────────────────────────────────────────────────────────────────────

BONDS = {
    "TNX":  {"symbol": "^TNX",  "name": "US Treasury 10-Year Yield", "maturity": "10Y", "country": "US"},
    "TYX":  {"symbol": "^TYX",  "name": "US Treasury 30-Year Yield", "maturity": "30Y", "country": "US"},
    "FVX":  {"symbol": "^FVX",  "name": "US Treasury 5-Year Yield",  "maturity": "5Y",  "country": "US"},
    "IRX":  {"symbol": "^IRX",  "name": "US Treasury 13-Week Yield", "maturity": "3M",  "country": "US"},
    "TNX2": {"symbol": "^TNX",  "name": "US Treasury 2-Year Yield",  "maturity": "2Y",  "country": "US"},
}


# ── COMMODITIES ────────────────────────────────────────────────────────────────

COMMODITIES = {
    "GOLD":    {"symbol": "GC=F",  "name": "Gold Futures",              "unit": "USD/oz",     "sector": "Precious Metals"},
    "SILVER":  {"symbol": "SI=F",  "name": "Silver Futures",            "unit": "USD/oz",     "sector": "Precious Metals"},
    "PLATINUM":{"symbol": "PL=F",  "name": "Platinum Futures",          "unit": "USD/oz",     "sector": "Precious Metals"},
    "OIL":     {"symbol": "CL=F",  "name": "Crude Oil WTI Futures",     "unit": "USD/barrel", "sector": "Energy"},
    "BRENT":   {"symbol": "BZ=F",  "name": "Brent Crude Oil Futures",   "unit": "USD/barrel", "sector": "Energy"},
    "NATGAS":  {"symbol": "NG=F",  "name": "Natural Gas Futures",       "unit": "USD/MMBtu",  "sector": "Energy"},
    "COPPER":  {"symbol": "HG=F",  "name": "Copper Futures",            "unit": "USD/lb",     "sector": "Industrial Metals"},
    "WHEAT":   {"symbol": "ZW=F",  "name": "Wheat Futures",             "unit": "USD/bushel", "sector": "Agriculture"},
    "CORN":    {"symbol": "ZC=F",  "name": "Corn Futures",              "unit": "USD/bushel", "sector": "Agriculture"},
    "SOYBEAN": {"symbol": "ZS=F",  "name": "Soybean Futures",           "unit": "USD/bushel", "sector": "Agriculture"},
    "COFFEE":  {"symbol": "KC=F",  "name": "Coffee Futures",            "unit": "USD/lb",     "sector": "Agriculture"},
    "SUGAR":   {"symbol": "SB=F",  "name": "Sugar Futures",             "unit": "USD/lb",     "sector": "Agriculture"},
    "COTTON":  {"symbol": "CT=F",  "name": "Cotton Futures",            "unit": "USD/lb",     "sector": "Agriculture"},
}


# ── CRYPTO ─────────────────────────────────────────────────────────────────────

CRYPTO = {
    "BTC":   {"symbol": "BTC-USD",  "name": "Bitcoin"},
    "ETH":   {"symbol": "ETH-USD",  "name": "Ethereum"},
    "BNB":   {"symbol": "BNB-USD",  "name": "Binance Coin"},
    "SOL":   {"symbol": "SOL-USD",  "name": "Solana"},
    "XRP":   {"symbol": "XRP-USD",  "name": "Ripple"},
    "ADA":   {"symbol": "ADA-USD",  "name": "Cardano"},
    "DOGE":  {"symbol": "DOGE-USD", "name": "Dogecoin"},
    "DOT":   {"symbol": "DOT-USD",  "name": "Polkadot"},
    "MATIC": {"symbol": "MATIC-USD","name": "Polygon"},
    "AVAX":  {"symbol": "AVAX-USD", "name": "Avalanche"},
    "LINK":  {"symbol": "LINK-USD", "name": "Chainlink"},
    "ATOM":  {"symbol": "ATOM-USD", "name": "Cosmos"},
    "UNI":   {"symbol": "UNI-USD",  "name": "Uniswap"},
}


# ── INDICES ────────────────────────────────────────────────────────────────────

INDICES = {
    "SPX":    {"symbol": "^GSPC",   "name": "S&P 500"},
    "DJI":    {"symbol": "^DJI",    "name": "Dow Jones Industrial Average"},
    "NASDAQ": {"symbol": "^IXIC",   "name": "NASDAQ Composite"},
    "VIX":    {"symbol": "^VIX",    "name": "CBOE Volatility Index"},
    "NIFTY":  {"symbol": "^NSEI",   "name": "Nifty 50 (India)"},
    "SENSEX": {"symbol": "^BSESN",  "name": "BSE Sensex (India)"},
    "FTSE":   {"symbol": "^FTSE",   "name": "FTSE 100 (UK)"},
    "DAX":    {"symbol": "^GDAXI",  "name": "DAX (Germany)"},
    "NIKKEI": {"symbol": "^N225",   "name": "Nikkei 225 (Japan)"},
    "HSI":    {"symbol": "^HSI",    "name": "Hang Seng (Hong Kong)"},
    "SSE":    {"symbol": "000001.SS","name": "Shanghai Composite (China)"},
}


# ── TICKER RESOLUTION ──────────────────────────────────────────────────────────

def normalize_ticker(ticker: str) -> str:
    """Normalize user input: EUR/USD, EUR-USD, EURUSD → EURUSD"""
    return ticker.upper().replace("/", "").replace("-", "").replace(" ", "").strip()


def resolve_ticker(user_input: str) -> Tuple[str, AssetClass, Dict]:
    """
    Resolve user input to (yfinance_symbol, asset_class, metadata).
    Falls through registries in priority order, defaults to EQUITY.
    """
    normalized = normalize_ticker(user_input)
    
    if normalized in FOREX_PAIRS:
        meta = FOREX_PAIRS[normalized]
        return meta["symbol"], AssetClass.FOREX, meta
    
    if normalized in BONDS:
        meta = BONDS[normalized]
        return meta["symbol"], AssetClass.BOND, meta
    
    if normalized in COMMODITIES:
        meta = COMMODITIES[normalized]
        return meta["symbol"], AssetClass.COMMODITY, meta
    
    if normalized in CRYPTO:
        meta = CRYPTO[normalized]
        return meta["symbol"], AssetClass.CRYPTO, meta
    
    if normalized in INDICES:
        meta = INDICES[normalized]
        return meta["symbol"], AssetClass.INDEX, meta
    
    # Try to detect forex-like patterns (6 chars, all alpha)
    # e.g. user types "INRUSD" but it's not in our registry
    if len(normalized) == 6 and normalized.isalpha():
        # Try as forex pair on yfinance
        return f"{normalized}=X", AssetClass.FOREX, {
            "symbol": f"{normalized}=X",
            "name": f"{normalized[:3]} / {normalized[3:]}",
            "base": normalized[:3],
            "quote": normalized[3:],
        }
    
    # Try to detect crypto patterns (ends with common crypto suffixes)
    if normalized.endswith("USD") and len(normalized) <= 8 and normalized[:-3].isalpha():
        crypto_base = normalized[:-3]
        if len(crypto_base) >= 2:
            # Could be crypto — try as crypto pair
            return f"{crypto_base}-USD", AssetClass.CRYPTO, {
                "symbol": f"{crypto_base}-USD",
                "name": crypto_base,
            }
    
    # Default to EQUITY
    return user_input.upper(), AssetClass.EQUITY, {}


def get_asset_display_name(ticker: str, asset_class: AssetClass, metadata: Dict) -> str:
    """Get a human-readable name for display."""
    if asset_class == AssetClass.FOREX:
        return f"{metadata.get('base')}/{metadata.get('quote')}"
    elif asset_class in [AssetClass.BOND, AssetClass.COMMODITY, AssetClass.CRYPTO, AssetClass.INDEX]:
        return metadata.get("name", ticker)
    else:
        return ticker


# ── ASSET-SPECIFIC PROJECTION PARAMETERS ──────────────────────────────────────

def get_projection_params(asset_class: AssetClass) -> Dict:
    params = {
        AssetClass.EQUITY: {"low_multiplier": 0.5, "high_multiplier": 2.0, "default_horizon": 5},
        AssetClass.FOREX: {"low_multiplier": 0.90, "high_multiplier": 1.10, "default_horizon": 1},
        AssetClass.BOND: {"low_multiplier": 0.95, "high_multiplier": 1.08, "default_horizon": 3},
        AssetClass.COMMODITY: {"low_multiplier": 0.60, "high_multiplier": 1.80, "default_horizon": 2},
        AssetClass.CRYPTO: {"low_multiplier": 0.20, "high_multiplier": 5.0, "default_horizon": 1},
        AssetClass.INDEX: {"low_multiplier": 0.6, "high_multiplier": 1.8, "default_horizon": 5},
    }
    return params.get(asset_class, params[AssetClass.EQUITY])


def is_valid_ticker(ticker: str) -> bool:
    return True  # Let yfinance validate


def get_all_asset_symbols() -> Dict[AssetClass, list]:
    return {
        AssetClass.FOREX: list(FOREX_PAIRS.keys()),
        AssetClass.BOND: list(BONDS.keys()),
        AssetClass.COMMODITY: list(COMMODITIES.keys()),
        AssetClass.CRYPTO: list(CRYPTO.keys()),
        AssetClass.INDEX: list(INDICES.keys()),
    }


# ── SEARCH ─────────────────────────────────────────────────────────────────────

def search_assets(query: str, limit: int = 15) -> List[Dict]:
    """
    Search across all registries by ticker or name.
    Returns a list of {ticker, name, asset_class, yf_symbol}.
    Case-insensitive, partial match on ticker and name.
    """
    q = query.upper().replace("/", "").replace("-", "").strip()
    q_lower = query.lower()
    results = []
    
    registries = [
        (FOREX_PAIRS, "FOREX"),
        (BONDS, "BOND"),
        (COMMODITIES, "COMMODITY"),
        (CRYPTO, "CRYPTO"),
        (INDICES, "INDEX"),
    ]
    
    for registry, asset_class in registries:
        for ticker, meta in registry.items():
            name = meta.get("name", "")
            # Match on ticker prefix or name substring
            if (
                ticker.startswith(q) or
                q in ticker or
                q_lower in name.lower()
            ):
                results.append({
                    "ticker": ticker,
                    "name": name,
                    "asset_class": asset_class,
                    "yf_symbol": meta.get("symbol", ticker),
                })
    
    # Sort: exact prefix matches first, then alphabetical
    results.sort(key=lambda r: (
        0 if r["ticker"].startswith(q) else 1,
        r["ticker"],
    ))
    
    return results[:limit]
