# =============================================================
# src/ingestion/sec_client.py
#
# Fetches SEC filings from the EDGAR REST API.
#
# WHY SEC FILINGS MATTER FOR FINTRAC:
# This is what fixes the "Mistral doesn't know about current
# events" gap. A 10-K contains management's discussion of risks,
# revenue breakdown, debt, and forward guidance — all written by
# the company itself. An 8-K is filed within 4 business days of
# any material event (earnings miss, CEO resignation, merger).
# Once these are in ChromaDB, Mistral can reason over them.
#
# EDGAR API — NO KEY REQUIRED:
# SEC EDGAR is a public government API. No authentication needed.
# The only requirement is a descriptive User-Agent header with
# a contact email — SEC uses this to identify scrapers.
# Rate limit: 10 requests/second. We stay well under that.
#
# THREE ENDPOINTS WE USE:
# 1. company_tickers.json  → maps ticker symbols to CIK numbers
# 2. submissions/{CIK}.json → lists all filings for a company
# 3. Archives/{CIK}/{accession}/ → the actual filing documents
#
# WHAT IS A CIK?
# Central Index Key — SEC's internal ID for every registered
# entity. XOM's CIK is 0000034088. We need it to look up filings.
# =============================================================

import asyncio
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx
from loguru import logger


# ── CONSTANTS ──────────────────────────────────────────────────────────────────
EDGAR_BASE       = "https://data.sec.gov"
EDGAR_ARCHIVES   = "https://www.sec.gov/Archives/edgar/full-index"
TICKERS_URL      = "https://www.sec.gov/files/company_tickers.json"

# SEC requires this header — use your own contact email in production
HEADERS = {
    "User-Agent": "FinTrac-Dev research@fintrac.local",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

# Filing types we care about
TARGET_FORMS = {"10-K", "10-K/A", "8-K", "8-K/A"}

# Thread pool for blocking HTTP calls
_thread_pool = ThreadPoolExecutor(max_workers=3)


# ── DATA CLASSES ───────────────────────────────────────────────────────────────
# Plain dataclasses (not Pydantic) because these are internal
# transfer objects — they never touch the API boundary.

@dataclass
class FilingMetadata:
    """Metadata about a single SEC filing."""
    cik:              str
    ticker:           str
    form_type:        str       # 10-K, 8-K etc.
    accession_number: str       # e.g. 0000034088-24-000012
    filed_date:       datetime
    document_url:     str       # URL to the primary document
    description:      str = "" # filing description from EDGAR index


@dataclass
class FilingText:
    """Downloaded and extracted text from a filing."""
    metadata:     FilingMetadata
    raw_text:     str
    word_count:   int
    content_hash: str           # SHA-256 of raw_text — deduplication key


# ── CIK LOOKUP ─────────────────────────────────────────────────────────────────
# company_tickers.json is a flat dict of all SEC-registered companies.
# We cache it in memory after the first fetch — it's ~5MB and changes
# infrequently. No need to hit the API on every request.

_ticker_to_cik_cache: dict[str, str] = {}


def _fetch_ticker_map_sync() -> dict[str, str]:
    """
    Fetch the full ticker→CIK mapping from SEC.
    Returns a dict: {"XOM": "0000034088", "AAPL": "0000320193", ...}
    CIKs are zero-padded to 10 digits as required by the submissions API.
    """
    response = httpx.get(TICKERS_URL, headers={"User-Agent": HEADERS["User-Agent"]},
                         timeout=30)
    response.raise_for_status()

    data = response.json()
    # The JSON structure is: {"0": {"cik_str": 34088, "ticker": "XOM", ...}, ...}
    mapping = {}
    for entry in data.values():
        ticker = entry.get("ticker", "").upper()
        cik    = str(entry.get("cik_str", "")).zfill(10)  # zero-pad to 10 digits
        if ticker:
            mapping[ticker] = cik

    logger.info(f"Loaded {len(mapping)} ticker→CIK mappings from SEC EDGAR")
    return mapping


async def get_cik_for_ticker(ticker: str) -> Optional[str]:
    """
    Resolve a ticker symbol to its SEC CIK number.
    Returns zero-padded 10-digit string e.g. "0000034088", or None.
    """
    global _ticker_to_cik_cache

    ticker = ticker.upper().strip()

    # Return from cache if available
    if ticker in _ticker_to_cik_cache:
        return _ticker_to_cik_cache[ticker]

    # Fetch the full map and cache it
    loop = asyncio.get_event_loop()
    try:
        mapping = await loop.run_in_executor(_thread_pool, _fetch_ticker_map_sync)
        _ticker_to_cik_cache.update(mapping)
    except Exception as e:
        logger.error(f"Failed to fetch ticker→CIK map: {e}")
        return None

    cik = _ticker_to_cik_cache.get(ticker)
    if not cik:
        logger.warning(f"No CIK found for ticker {ticker}")
    return cik


# ── FILING LIST ────────────────────────────────────────────────────────────────

def _fetch_filings_sync(cik: str, ticker: str,
                         form_types: set[str],
                         max_filings: int) -> list[FilingMetadata]:
    """
    Fetch the list of recent filings for a CIK from the submissions API.
    The submissions endpoint returns the most recent 1000 filings.
    """
    url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
    headers = {**HEADERS, "Host": "data.sec.gov"}

    response = httpx.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    data     = response.json()
    filings  = data.get("filings", {}).get("recent", {})

    forms       = filings.get("form", [])
    dates       = filings.get("filingDate", [])
    accessions  = filings.get("accessionNumber", [])
    descriptions = filings.get("primaryDocument", [])

    results = []
    for form, date_str, accession, doc in zip(forms, dates, accessions, descriptions):
        if form not in form_types:
            continue

        # Accession number format in URLs: remove dashes
        accession_nodash = accession.replace("-", "")

        # Primary document URL
        doc_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(cik)}/{accession_nodash}/{doc}"
        )

        try:
            filed_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            filed_date = datetime.utcnow()

        results.append(FilingMetadata(
            cik              = cik,
            ticker           = ticker,
            form_type        = form,
            accession_number = accession,
            filed_date       = filed_date,
            document_url     = doc_url,
            description      = doc,
        ))

        if len(results) >= max_filings:
            break

    logger.info(f"Found {len(results)} filings for {ticker} (CIK: {cik})")
    return results


async def get_recent_filings(
    ticker:      str,
    form_types:  set[str] = TARGET_FORMS,
    max_filings: int = 5,
) -> list[FilingMetadata]:
    """
    Get the most recent SEC filings for a ticker.
    Returns up to max_filings results across all requested form types.
    """
    cik = await get_cik_for_ticker(ticker)
    if not cik:
        return []

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            _thread_pool,
            _fetch_filings_sync,
            cik, ticker, form_types, max_filings,
        )
    except Exception as e:
        logger.error(f"Failed to fetch filings for {ticker}: {e}")
        return []


# ── DOCUMENT DOWNLOAD & TEXT EXTRACTION ───────────────────────────────────────

def _download_and_extract_sync(filing: FilingMetadata) -> Optional[FilingText]:
    """
    Download a filing document and extract clean text.

    WHY TEXT EXTRACTION IS MESSY:
    SEC filings are submitted as HTML, XBRL, or plain text.
    10-K filings in particular are enormous HTML documents with
    inline XBRL tags, tables, and boilerplate legal language.
    We strip all of that and keep only readable prose, because
    that's what the LLM can actually reason over.
    """
    headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Host": "www.sec.gov",
    }

    try:
        response = httpx.get(filing.document_url, headers=headers,
                             timeout=60, follow_redirects=True)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to download {filing.document_url}: {e}")
        return None

    raw_content = response.text

    # ── TEXT CLEANING ──────────────────────────────────────────
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", raw_content)

    # Remove XBRL inline tags (look like <ix:nonNumeric ...>)
    text = re.sub(r"<ix:[^>]+>", " ", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Remove boilerplate header lines (page numbers, form headers)
    text = re.sub(r"(?i)(table of contents|form 10-k|united states securities)", "", text)

    # Truncate at 50,000 characters — enough for meaningful context
    # without blowing up the ChromaDB embedding or the LLM context window.
    # A typical 10-K is 200,000+ characters — we take the first 50k
    # which covers the business description and risk factors sections.
    if len(text) > 50_000:
        logger.debug(
            f"Truncating {filing.form_type} for {filing.ticker} "
            f"from {len(text)} to 50,000 chars"
        )
        text = text[:50_000]

    if len(text) < 500:
        logger.warning(
            f"Extracted text too short ({len(text)} chars) for "
            f"{filing.form_type} {filing.accession_number} — skipping"
        )
        return None

    content_hash = hashlib.sha256(text.encode()).hexdigest()
    word_count   = len(text.split())

    logger.info(
        f"Extracted {word_count} words from {filing.form_type} "
        f"for {filing.ticker} ({filing.filed_date.date()})"
    )

    return FilingText(
        metadata     = filing,
        raw_text     = text,
        word_count   = word_count,
        content_hash = content_hash,
    )


async def download_filing(filing: FilingMetadata) -> Optional[FilingText]:
    """
    Async wrapper: download and extract text from a single filing.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _thread_pool,
        _download_and_extract_sync,
        filing,
    )


async def fetch_filings_with_text(
    ticker:      str,
    form_types:  set[str] = TARGET_FORMS,
    max_filings: int = 3,
) -> list[FilingText]:
    """
    High-level entry point: get recent filings AND their text.
    Downloads up to max_filings documents concurrently.

    This is what document_ingester.py calls.
    """
    filings = await get_recent_filings(ticker, form_types, max_filings)
    if not filings:
        return []

    # Download all concurrently — asyncio.gather fires them in parallel
    texts = await asyncio.gather(*[download_filing(f) for f in filings])

    # Filter out None results (download failures)
    valid = [t for t in texts if t is not None]
    logger.info(
        f"Successfully downloaded {len(valid)}/{len(filings)} "
        f"filings for {ticker}"
    )
    return valid