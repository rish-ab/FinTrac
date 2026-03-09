# =============================================================
# src/agent/rag_pipeline.py
#
# The RAG (Retrieval Augmented Generation) pipeline.
#
# WHAT IS RAG AND WHY DOES IT SOLVE THE NEWS GAP?
# Mistral's training data has a cutoff — it knows nothing about
# XOM's Feb 2026 10-K, Hormuz closure risk, or this week's
# earnings. RAG fixes this by:
#   1. Storing the actual documents as vector embeddings
#   2. At query time, finding the most relevant passages
#   3. Injecting those passages into the prompt as context
#
# Mistral then reasons over real, current text rather than
# its stale training memory. The difference is significant:
#
# WITHOUT RAG:
#   "XOM has historically strong cash flows..." (training data)
#
# WITH RAG:
#   "Per XOM's 10-K filed Feb 2026, management flagged energy
#    transition as a top-3 risk, and Permian Basin capex is
#    projected at $28B..." (actual filing text)
#
# HOW VECTOR SEARCH WORKS:
# Text is converted to a list of ~768 numbers (a vector) by
# nomic-embed-text. Similar meaning → similar numbers → close
# together in vector space. ChromaDB finds the closest vectors
# to the query vector. This is semantic search — it finds
# relevant passages even if they don't share exact keywords.
#
# CHUNKING:
# We can't embed an entire 10-K as one vector — it's too long
# and the signal gets diluted. We split into overlapping chunks
# of ~500 tokens. Overlap ensures a sentence at the boundary
# of two chunks isn't lost.
# =============================================================

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_ollama import OllamaEmbeddings
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.ingestion.document_ingester import (
    get_pending_documents,
    mark_document_embedded,
    mark_document_failed,
)


# ── THREAD POOL ────────────────────────────────────────────────────────────────
# ChromaDB and embedding calls are synchronous — run in thread pool
_thread_pool = ThreadPoolExecutor(max_workers=2)


# ── CHROMADB CLIENT ────────────────────────────────────────────────────────────
# PersistentClient stores the vector index to disk at CHROMA_PATH.
# This means embeddings survive container restarts — you don't
# re-embed every time the app starts.
#
# anonymized_telemetry=False — ChromaDB by default phones home
# with usage stats. We disable this for privacy.

CHROMA_PATH = Path("data/lake/chroma_db")
CHROMA_PATH.mkdir(parents=True, exist_ok=True)

_chroma_client = chromadb.PersistentClient(
    path=str(CHROMA_PATH),
    settings=ChromaSettings(anonymized_telemetry=False),
)

# One collection holds all financial documents.
# Collection = a named namespace in ChromaDB, like a table.
# get_or_create means it's safe to call on every startup.
_collection = _chroma_client.get_or_create_collection(
    name="fintrac_documents",
    metadata={"hnsw:space": "cosine"},  # cosine similarity for text
)


# ── EMBEDDINGS MODEL ───────────────────────────────────────────────────────────
# nomic-embed-text is a dedicated embedding model — much better
# than using the main LLM for embeddings.
# It produces 768-dimensional vectors optimised for retrieval.
# Make sure you've pulled it: ollama pull nomic-embed-text

_embeddings = OllamaEmbeddings(
    model    = settings.OLLAMA_EMBED_MODEL,   # "nomic-embed-text"
    base_url = settings.OLLAMA_BASE_URL,
)


# ── TEXT CHUNKING ──────────────────────────────────────────────────────────────
# Splits a long document into overlapping chunks.
#
# WHY OVERLAP?
# If a key sentence is at the boundary of two chunks, neither
# chunk alone captures its full context. Overlap of ~50 tokens
# ensures boundary content appears in at least one complete chunk.
#
# chunk_size=500    tokens ≈ ~375 words ≈ ~2000 characters
# overlap=50        tokens ≈ ~37 words

def _chunk_text(
    text:       str,
    chunk_size: int = 500,
    overlap:    int = 50,
) -> list[str]:
    """
    Split text into overlapping word-based chunks.
    Returns a list of chunk strings.
    """
    # Collapse excessive whitespace first
    text = re.sub(r'\s+', ' ', text).strip()

    words  = text.split()
    chunks = []
    start  = 0

    while start < len(words):
        end   = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])

        # Skip chunks that are too short to be meaningful
        if len(chunk) > 100:
            chunks.append(chunk)

        # Move forward by (chunk_size - overlap) to create overlap
        start += chunk_size - overlap

    return chunks


# ── EMBED AND STORE ONE DOCUMENT ───────────────────────────────────────────────

def _embed_document_sync(
    document_id:   str,
    raw_text_path: str,
    ticker:        str,
    doc_type:      str,
    filed_at:      str,
) -> int:
    """
    Synchronous embedding worker — runs in thread pool.

    Steps:
      1. Read text from disk
      2. Split into chunks
      3. Embed all chunks via nomic-embed-text
      4. Store in ChromaDB with metadata
      5. Return number of chunks stored
    """
    path = Path(raw_text_path)
    if not path.exists():
        raise FileNotFoundError(f"Document file not found: {raw_text_path}")

    text   = path.read_text(encoding="utf-8")
    chunks = _chunk_text(text)

    if not chunks:
        raise ValueError(f"No chunks generated from {raw_text_path}")

    logger.info(
        f"Embedding {len(chunks)} chunks for {ticker} {doc_type} "
        f"(doc_id: {document_id[:8]}...)"
    )

    # Build ChromaDB inputs
    # ids must be unique across the collection — use doc_id + chunk index
    ids        = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
    metadatas  = [
        {
            "document_id": document_id,
            "ticker":      ticker,
            "doc_type":    doc_type,
            "filed_at":    filed_at,
            "chunk_index": i,
            "chunk_total": len(chunks),
        }
        for i in range(len(chunks))
    ]

    # Embed all chunks — OllamaEmbeddings.embed_documents() handles batching
    embeddings = _embeddings.embed_documents(chunks)

    # Upsert into ChromaDB
    # Upsert = insert if not exists, update if exists — idempotent
    _collection.upsert(
        ids        = ids,
        embeddings = embeddings,
        documents  = chunks,
        metadatas  = metadatas,
    )

    logger.info(
        f"Stored {len(chunks)} vectors in ChromaDB for "
        f"{ticker} {doc_type}"
    )
    return len(chunks)


async def embed_document(
    document_id:   str,
    raw_text_path: str,
    ticker:        str,
    doc_type:      str,
    filed_at:      str,
) -> int:
    """Async wrapper for the embedding worker."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _thread_pool,
        _embed_document_sync,
        document_id,
        raw_text_path,
        ticker,
        doc_type,
        filed_at,
    )


# ── PROCESS PENDING DOCUMENTS ──────────────────────────────────────────────────
# This is the function main.py calls at startup and the scheduled
# job calls periodically to drain the PENDING queue.

async def process_pending_documents(db: AsyncSession, batch_size: int = 10) -> int:
    """
    Find all PENDING documents in MariaDB and embed them into ChromaDB.
    Marks each document DONE or FAILED in MariaDB.
    Returns total number of chunks embedded.
    """
    pending = await get_pending_documents(db, limit=batch_size)

    if not pending:
        logger.info("No pending documents to embed")
        return 0

    logger.info(f"Processing {len(pending)} pending documents for embedding")

    total_chunks = 0
    for doc in pending:
        # Extract ticker from asset relationship or fall back to path parsing
        # e.g. data/lake/documents/XOM/10-K/... → "XOM"
        ticker = "UNKNOWN"
        if doc.raw_text_path:
            parts = Path(doc.raw_text_path).parts
            # Structure: data/lake/documents/{ticker}/{doc_type}/file.txt
            if len(parts) >= 4:
                ticker = parts[3]   # index 3 = ticker folder

        filed_at_str = doc.filed_at.isoformat() if doc.filed_at else "unknown"

        try:
            chunks = await embed_document(
                document_id   = doc.id,
                raw_text_path = doc.raw_text_path,
                ticker        = ticker,
                doc_type      = doc.doc_type,
                filed_at      = filed_at_str,
            )
            await mark_document_embedded(doc.id, db)
            total_chunks += chunks

        except Exception as e:
            logger.error(
                f"Failed to embed document {doc.id} "
                f"({ticker} {doc.doc_type}): {e}"
            )
            await mark_document_failed(doc.id, db, reason=str(e))

    logger.info(
        f"Embedding complete: {total_chunks} total chunks "
        f"across {len(pending)} documents"
    )
    return total_chunks


# ── RETRIEVAL ──────────────────────────────────────────────────────────────────
# Given a query string and ticker, find the most relevant
# passages from all embedded documents for that ticker.
#
# WHY FILTER BY TICKER?
# We don't want XOM's 10-K passages appearing in an AAPL query.
# ChromaDB's where filter restricts results to documents for
# the specific company being analysed.

def _retrieve_sync(
    query:   str,
    ticker:  str,
    top_k:   int = 5,
) -> list[dict]:
    """
    Synchronous retrieval worker.
    Embeds the query, searches ChromaDB, returns top_k passages.
    """
    # Embed the query with the same model used for documents
    query_embedding = _embeddings.embed_query(query)

    # Query ChromaDB — filter by ticker so we only get relevant company docs
    results = _collection.query(
        query_embeddings = [query_embedding],
        n_results        = top_k,
        where            = {"ticker": ticker},
        include          = ["documents", "metadatas", "distances"],
    )

    if not results["documents"] or not results["documents"][0]:
        return []

    passages = []
    for doc, meta, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        # distance in cosine space: 0 = identical, 2 = opposite
        # Convert to similarity score: 1 = perfect match
        similarity = round(1 - (distance / 2), 3)

        passages.append({
            "text":        doc,
            "ticker":      meta.get("ticker"),
            "doc_type":    meta.get("doc_type"),
            "filed_at":    meta.get("filed_at"),
            "chunk_index": meta.get("chunk_index"),
            "similarity":  similarity,
        })

    return passages


async def retrieve_context(
    query:  str,
    ticker: str,
    top_k:  int = 5,
) -> list[dict]:
    """
    Async wrapper: retrieve the most relevant document passages
    for a given query and ticker.

    Returns list of passage dicts with text, source, and similarity score.
    Returns empty list if no documents are embedded for this ticker.
    """
    loop = asyncio.get_event_loop()
    try:
        passages = await loop.run_in_executor(
            _thread_pool,
            _retrieve_sync,
            query, ticker, top_k,
        )

        if passages:
            logger.info(
                f"Retrieved {len(passages)} passages for {ticker} "
                f"(top similarity: {passages[0]['similarity']})"
            )
        else:
            logger.info(f"No embedded documents found for {ticker}")

        return passages

    except Exception as e:
        logger.error(f"RAG retrieval failed for {ticker}: {e}")
        return []


# ── CONTEXT FORMATTER ──────────────────────────────────────────────────────────
# Converts retrieved passages into a clean string for injection
# into the Mistral prompt. Lives here because it's RAG-layer logic.

def format_rag_context(passages: list[dict]) -> str:
    """
    Format retrieved passages into a readable prompt block.
    Each passage is labelled with its source and filing date
    so Mistral can cite sources in its reasoning.
    """
    if not passages:
        return "No SEC filing context available for this ticker."

    lines = ["=== RETRIEVED FILING CONTEXT (most relevant passages) ==="]
    for i, p in enumerate(passages, 1):
        lines.append(
            f"\n[Source {i}: {p['doc_type']} filed {p['filed_at'][:10]} "
            f"| relevance: {p['similarity']:.0%}]\n{p['text']}"
        )

    lines.append("\n=== END FILING CONTEXT ===")
    return "\n".join(lines)


# ── STARTUP INIT ───────────────────────────────────────────────────────────────

async def init_vector_store(db: AsyncSession) -> None:
    """
    Called from main.py lifespan on startup.
    Reports current ChromaDB state and processes any pending documents
    that were ingested before the last shutdown.
    """
    count = _collection.count()
    logger.info(f"ChromaDB initialised — {count} vectors in collection")

    # Process any documents that were ingested but not yet embedded
    # (e.g. app crashed mid-run last session)
    if count == 0:
        logger.info("Empty vector store — checking for pending documents...")

    await process_pending_documents(db, batch_size=20)