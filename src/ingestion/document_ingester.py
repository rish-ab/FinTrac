# =============================================================
# src/ingestion/document_ingester.py
#
# Orchestrates the full ingestion pipeline for SEC filings:
#
#   1. Call sec_client to fetch filing text
#   2. Save raw text to data/lake/documents/ on disk
#   3. Write IngestionLog row to MariaDB
#   4. Write DocumentRegistry row to MariaDB
#   5. Mark embedding_status = "PENDING" (RAG pipeline picks up next)
#
# WHY DISK + DB?
# The raw text files on disk are the source of truth for the
# embedding pipeline. MariaDB tracks metadata (what was ingested,
# when, status) so we can query "which documents need embedding?"
# without scanning the filesystem.
#
# IDEMPOTENCY:
# Running this twice for the same ticker should not create
# duplicate rows. We check content_hash before inserting —
# if we've seen this exact document before, we skip it.
# This makes the ingester safe to run on a schedule.
# =============================================================

import os
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    AssetMaster,
    DocumentRegistry,
    IngestionLog,
)
from src.ingestion.sec_client import FilingText, fetch_filings_with_text


# ── STORAGE PATH ───────────────────────────────────────────────────────────────
# Documents land in data/lake/documents/{ticker}/{form_type}/
# e.g. data/lake/documents/XOM/10-K/0000034088-24-000012.txt
# The directory is created if it doesn't exist.

DOCUMENTS_BASE = Path("data/lake/documents")


def _get_doc_path(ticker: str, form_type: str, accession: str) -> Path:
    """Build the filesystem path for a filing's raw text."""
    safe_form = form_type.replace("/", "_")   # 10-K/A → 10-K_A
    safe_acc  = accession.replace("-", "_")
    directory = DOCUMENTS_BASE / ticker / safe_form
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{safe_acc}.txt"


# ── ASSET LOOKUP ───────────────────────────────────────────────────────────────

async def _get_asset_id(ticker: str, db: AsyncSession) -> str | None:
    """
    Look up the asset_id for a ticker in AssetMaster.
    Returns None if the ticker isn't registered yet.
    We don't auto-create AssetMaster rows here — that's the
    responsibility of a separate asset seeding step.
    """
    result = await db.execute(
        select(AssetMaster.asset_id)
        .where(AssetMaster.ticker_symbol == ticker.upper())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row


# ── DEDUPLICATION CHECK ────────────────────────────────────────────────────────

async def _document_exists(content_hash: str, db: AsyncSession) -> bool:
    """
    Check if we've already ingested this exact document.
    Uses content_hash (SHA-256) as the deduplication key.
    source_url stores the hash for lookup.
    """
    result = await db.execute(
        select(DocumentRegistry.id)
        .where(DocumentRegistry.source_url.contains(content_hash))
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


# ── SAVE ONE FILING ────────────────────────────────────────────────────────────

async def _save_filing(
    filing_text: FilingText,
    asset_id:    str | None,
    db:          AsyncSession,
) -> DocumentRegistry | None:
    """
    Persist a single filing:
      1. Skip if already ingested (idempotency)
      2. Write text to disk
      3. Create IngestionLog
      4. Create DocumentRegistry
    Returns the DocumentRegistry row or None if skipped.
    """
    meta = filing_text.metadata

    # ── IDEMPOTENCY CHECK ─────────────────────────────────────
    if await _document_exists(filing_text.content_hash, db):
        logger.info(
            f"Skipping {meta.form_type} {meta.accession_number} "
            f"for {meta.ticker} — already ingested"
        )
        return None

    # ── WRITE TO DISK ─────────────────────────────────────────
    doc_path = _get_doc_path(meta.ticker, meta.form_type, meta.accession_number)
    doc_path.write_text(filing_text.raw_text, encoding="utf-8")
    logger.info(f"Saved filing text to {doc_path}")

    # ── INGESTION LOG ─────────────────────────────────────────
    # Records the fetch operation itself — when it happened, which
    # API was used, and the path to the file we wrote.
    ingestion = IngestionLog(
        source_api          = "SEC_EDGAR",
        file_path_reference = str(doc_path),
        schema_hash         = filing_text.content_hash[:16],  # short prefix for display
        fetched_at          = datetime.utcnow(),
        status              = "SUCCESS",
    )
    db.add(ingestion)
    await db.flush()   # flush to get the ingestion_id before using it below

    # ── DOCUMENT REGISTRY ─────────────────────────────────────
    # Records the document's identity and current pipeline status.
    # embedding_status="PENDING" means the RAG pipeline hasn't
    # embedded this document into ChromaDB yet.
    #
    # We store content_hash in source_url alongside the real URL
    # so the deduplication check above can find it efficiently.
    document = DocumentRegistry(
        asset_id         = asset_id,
        doc_type         = meta.form_type.replace("/", "_"),   # 10-K/A → 10-K_A
        source_url       = f"{meta.document_url}|hash:{filing_text.content_hash}",
        filed_at         = meta.filed_date,
        ingestion_id     = ingestion.ingestion_id,
        raw_text_path    = str(doc_path),
        embedding_status = "PENDING",
    )
    db.add(document)
    await db.commit()

    logger.info(
        f"Registered {meta.form_type} for {meta.ticker} "
        f"({meta.filed_date.date()}) — embedding_status: PENDING"
    )
    return document


# ── PUBLIC ENTRY POINT ─────────────────────────────────────────────────────────

async def ingest_filings_for_ticker(
    ticker:      str,
    db:          AsyncSession,
    form_types:  set[str] | None = None,
    max_filings: int = 3,
) -> list[DocumentRegistry]:
    """
    Full ingestion pipeline for a ticker.
    Fetches, saves, and registers SEC filings in MariaDB.

    Returns list of newly created DocumentRegistry rows.
    Skips documents already ingested (idempotent).

    Called from:
      - analysis route (on-demand when user queries a ticker)
      - scheduled ingestion job (background refresh)
    """
    if form_types is None:
        form_types = {"10-K", "8-K"}

    logger.info(
        f"Starting SEC ingestion for {ticker} | "
        f"forms={form_types} | max={max_filings}"
    )

    # ── FETCH TEXT FROM EDGAR ──────────────────────────────────
    filing_texts = await fetch_filings_with_text(
        ticker      = ticker,
        form_types  = form_types,
        max_filings = max_filings,
    )

    if not filing_texts:
        logger.warning(f"No filings retrieved for {ticker}")
        return []

    # ── LOOK UP ASSET IN DB ────────────────────────────────────
    # asset_id may be None if this ticker hasn't been seeded yet.
    # We still save the document — it just won't have an asset FK.
    asset_id = await _get_asset_id(ticker, db)
    if not asset_id:
        logger.warning(
            f"Ticker {ticker} not found in asset_master — "
            f"document will be saved without asset_id FK"
        )

    # ── SAVE EACH FILING ───────────────────────────────────────
    saved = []
    for filing_text in filing_texts:
        doc = await _save_filing(filing_text, asset_id, db)
        if doc:
            saved.append(doc)

    logger.info(
        f"Ingestion complete for {ticker}: "
        f"{len(saved)} new documents, "
        f"{len(filing_texts) - len(saved)} skipped (duplicates)"
    )
    return saved


# ── PENDING DOCUMENTS QUERY ────────────────────────────────────────────────────

async def get_pending_documents(
    db:    AsyncSession,
    limit: int = 50,
) -> list[DocumentRegistry]:
    """
    Return documents waiting to be embedded into ChromaDB.
    Called by the RAG pipeline (Step 6) to find work to do.
    """
    result = await db.execute(
        select(DocumentRegistry)
        .where(DocumentRegistry.embedding_status == "PENDING")
        .order_by(DocumentRegistry.filed_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_document_embedded(
    document_id: str,
    db:          AsyncSession,
) -> None:
    """
    Mark a document as successfully embedded.
    Called by the RAG pipeline after ChromaDB ingestion.
    """
    result = await db.execute(
        select(DocumentRegistry).where(DocumentRegistry.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if doc:
        doc.embedding_status = "DONE"
        await db.commit()
        logger.info(f"Document {document_id} marked as DONE")


async def mark_document_failed(
    document_id: str,
    db:          AsyncSession,
    reason:      str = "",
) -> None:
    """
    Mark a document as failed embedding.
    Logged so the reconciliation job can retry or alert.
    """
    result = await db.execute(
        select(DocumentRegistry).where(DocumentRegistry.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if doc:
        doc.embedding_status = "FAILED"
        await db.commit()
        logger.error(f"Document {document_id} marked as FAILED: {reason}")