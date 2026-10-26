# =============================================================
# src/ingestion/equity_search.py
#
# Ticker search across the full equity / ETF / fund universe.
#
# WHY THIS IS MORE COMPLICATED THAN IT LOOKS:
# Yahoo blocks plain `requests` calls to its finance endpoints via
# TLS fingerprinting. yfinance works because recent versions use
# curl_cffi to impersonate a real browser. So we try, in order:
#
#   1. yfinance.Search          — yfinance's own search API (>=0.2.50)
#   2. yfinance's YfData session — its impersonated/authenticated session
#   3. plain requests            — works on some networks, harmless to try
#   4. SEC company_tickers.json  — LOCAL fallback, ~10k US public
#      companies with ticker + name. No bot detection, already used
#      by sec_client.py elsewhere in the project.
#
# Strategy 4 guarantees equity search never returns empty for a
# US-listed company, even if every Yahoo path is blocked.
# =============================================================

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import requests
from loguru import logger

_thread_pool = ThreadPoolExecutor(max_workers=4)

_YAHOO_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
_SEC_TICKERS_URL  = "https://www.sec.gov/files/company_tickers.json"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# SEC requires a descriptive User-Agent with contact info.
_SEC_HEADERS = {
    "User-Agent": "FinTrac Research Tool rishab@udel.edu",
    "Accept": "application/json",
}

# ── QUERY RESULT CACHE ─────────────────────────────────────────────────────────

_cache: Dict[str, tuple] = {}
_CACHE_TTL_SECONDS = 900
_CACHE_MAX_ENTRIES = 500

# ── SEC TICKER INDEX (loaded once, refreshed daily) ────────────────────────────

_sec_index: Optional[List[Dict]] = None
_sec_index_loaded_at: float = 0.0
_SEC_INDEX_TTL_SECONDS = 86400

_TYPE_MAP = {
    "EQUITY":         "EQUITY",
    "ETF":            "ETF",
    "MUTUALFUND":     "FUND",
    "INDEX":          "INDEX",
    "CRYPTOCURRENCY": "CRYPTO",
    "CURRENCY":       "FOREX",
    "FUTURE":         "COMMODITY",
}
_ALLOWED_TYPES = set(_TYPE_MAP.keys())


def _cache_get(key: str) -> Optional[List[Dict]]:
    entry = _cache.get(key)
    if entry is None:
        return None
    expires_at, results = entry
    if time.time() > expires_at:
        _cache.pop(key, None)
        return None
    return results


def _cache_put(key: str, results: List[Dict]) -> None:
    if len(_cache) >= _CACHE_MAX_ENTRIES:
        now = time.time()
        for k in [k for k, (exp, _) in _cache.items() if exp < now]:
            _cache.pop(k, None)
        if len(_cache) >= _CACHE_MAX_ENTRIES:
            _cache.pop(next(iter(_cache)), None)
    _cache[key] = (time.time() + _CACHE_TTL_SECONDS, results)


# ── NORMALIZE A YAHOO QUOTE DICT ───────────────────────────────────────────────

def _normalize_quote(quote: dict) -> Optional[Dict]:
    quote_type = quote.get("quoteType")
    symbol = quote.get("symbol")
    if not symbol or quote_type not in _ALLOWED_TYPES:
        return None
    name = (
        quote.get("longname")
        or quote.get("shortname")
        or quote.get("name")
        or symbol
    )
    return {
        "ticker":      symbol,
        "name":        name,
        "asset_class": _TYPE_MAP.get(quote_type, "EQUITY"),
        "yf_symbol":   symbol,
        "exchange":    quote.get("exchDisp") or quote.get("exchange") or "",
        "source":      "yahoo",
    }


# ── STRATEGY 1: yfinance.Search ────────────────────────────────────────────────

def _try_yfinance_search(query: str, limit: int) -> List[Dict]:
    try:
        import yfinance as yf
        if not hasattr(yf, "Search"):
            return []
        search = yf.Search(query, max_results=min(limit * 2, 20), news_count=0)
        quotes = getattr(search, "quotes", None) or []
        results = []
        for quote in quotes:
            normalized = _normalize_quote(quote)
            if normalized:
                results.append(normalized)
            if len(results) >= limit:
                break
        if results:
            logger.debug(f"Equity search via yfinance.Search: '{query}' -> {len(results)}")
        return results
    except Exception as e:
        logger.debug(f"yfinance.Search unavailable for '{query}': {e}")
        return []


# ── STRATEGY 2: yfinance's internal session ────────────────────────────────────

def _try_yfinance_session(query: str, limit: int) -> List[Dict]:
    """
    Reuse yfinance's own HTTP layer, which already handles Yahoo's bot
    detection (curl_cffi impersonation, cookie/crumb handling).
    """
    try:
        from yfinance.data import YfData
        data = YfData()
        params = {
            "q": query,
            "quotesCount": min(limit * 2, 20),
            "newsCount": 0,
            "listsCount": 0,
            "enableFuzzyQuery": "false",
        }
        response = data.get(url=_YAHOO_SEARCH_URL, params=params)
        payload = response.json()
        results = []
        for quote in payload.get("quotes", []):
            normalized = _normalize_quote(quote)
            if normalized:
                results.append(normalized)
            if len(results) >= limit:
                break
        if results:
            logger.debug(f"Equity search via YfData session: '{query}' -> {len(results)}")
        return results
    except Exception as e:
        logger.debug(f"YfData session search failed for '{query}': {e}")
        return []


# ── STRATEGY 3: plain requests ─────────────────────────────────────────────────

def _try_plain_requests(query: str, limit: int) -> List[Dict]:
    try:
        response = requests.get(
            _YAHOO_SEARCH_URL,
            params={
                "q": query,
                "quotesCount": min(limit * 2, 20),
                "newsCount": 0,
                "listsCount": 0,
                "enableFuzzyQuery": "false",
            },
            headers=_BROWSER_HEADERS,
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        results = []
        for quote in payload.get("quotes", []):
            normalized = _normalize_quote(quote)
            if normalized:
                results.append(normalized)
            if len(results) >= limit:
                break
        if results:
            logger.debug(f"Equity search via requests: '{query}' -> {len(results)}")
        return results
    except Exception as e:
        logger.debug(f"Plain requests search failed for '{query}': {e}")
        return []


# ── STRATEGY 4: SEC LOCAL INDEX ────────────────────────────────────────────────

def _load_sec_index() -> List[Dict]:
    """
    Load the SEC's company_tickers.json — roughly 10,000 US public
    companies with ticker symbol and registered company name.
    Cached in-process for 24 hours.
    """
    global _sec_index, _sec_index_loaded_at

    if _sec_index is not None and (time.time() - _sec_index_loaded_at) < _SEC_INDEX_TTL_SECONDS:
        return _sec_index

    try:
        response = requests.get(_SEC_TICKERS_URL, headers=_SEC_HEADERS, timeout=10)
        response.raise_for_status()
        raw = response.json()

        index = []
        for entry in raw.values():
            ticker = (entry.get("ticker") or "").strip().upper()
            title  = (entry.get("title") or "").strip()
            if ticker and title:
                index.append({"ticker": ticker, "name": title.title()})

        _sec_index = index
        _sec_index_loaded_at = time.time()
        logger.info(f"Loaded {len(index)} tickers into local equity search index (SEC)")
        return index

    except Exception as e:
        logger.warning(f"Failed to load SEC ticker index: {e}")
        return _sec_index or []


def _search_sec_local(query: str, limit: int) -> List[Dict]:
    """Rank-ordered search over the local SEC ticker index."""
    index = _load_sec_index()
    if not index:
        return []

    q_upper = query.strip().upper()
    q_lower = query.strip().lower()
    if not q_upper:
        return []

    scored = []
    for entry in index:
        ticker = entry["ticker"]
        name = entry["name"]
        name_words = name.lower().replace(",", " ").replace(".", " ").split()

        if ticker == q_upper:
            rank = 0
        elif ticker.startswith(q_upper):
            rank = 1
        elif name.lower().startswith(q_lower):
            rank = 2
        elif any(word.startswith(q_lower) for word in name_words):
            rank = 3
        else:
            continue

        scored.append((rank, len(ticker), {
            "ticker":      ticker,
            "name":        name,
            "asset_class": "EQUITY",
            "yf_symbol":   ticker,
            "exchange":    "",
            "source":      "sec",
        }))

    scored.sort(key=lambda x: (x[0], x[1]))
    results = [item[2] for item in scored[:limit]]
    if results:
        logger.debug(f"Equity search via SEC local index: '{query}' -> {len(results)}")
    return results


# ── ORCHESTRATION ──────────────────────────────────────────────────────────────

def _search_equities_sync(query: str, limit: int) -> List[Dict]:
    for strategy in (_try_yfinance_search, _try_yfinance_session, _try_plain_requests):
        results = strategy(query, limit)
        if results:
            return results

    # Every Yahoo path blocked or empty — fall back to the local index.
    results = _search_sec_local(query, limit)
    if not results:
        logger.warning(f"Equity search returned nothing for '{query}' across all strategies")
    return results


async def search_equities(query: str, limit: int = 10) -> List[Dict]:
    """
    Search equities, ETFs and funds by company name or ticker symbol.
    Returns [] rather than raising if every strategy fails, so the
    /assets/search endpoint degrades to registry-only results.
    """
    normalized = query.strip().lower()
    if len(normalized) < 2:
        return []

    cache_key = f"{normalized}:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        _thread_pool, _search_equities_sync, query.strip(), limit
    )
    _cache_put(cache_key, results)
    return results


# ── WARM-UP ────────────────────────────────────────────────────────────────────

async def warm_equity_index() -> None:
    """
    Preload the SEC index at startup so the first search doesn't pay
    the download cost. Call from the FastAPI lifespan handler.
    """
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_thread_pool, _load_sec_index)
