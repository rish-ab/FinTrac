# =============================================================
# src/db/session.py
#
# Database engine and session factory.
#
# THREE THINGS THIS FILE PROVIDES:
#
# 1. ENGINE
#    The connection pool to MariaDB. Created once at startup.
#    Manages N simultaneous connections efficiently — reuses
#    existing connections rather than opening a new TCP socket
#    on every request.
#
# 2. SESSION FACTORY
#    A factory that produces individual database sessions.
#    Each request gets its own session — isolated transaction
#    that either commits fully or rolls back on error.
#
# 3. get_db() DEPENDENCY
#    A FastAPI dependency that hands a session to a route
#    and guarantees it's closed after the request finishes,
#    even if an exception is raised.
#
# ASYNC vs SYNC:
# We use SQLAlchemy's async engine (create_async_engine) with
# aiomysql as the async MySQL driver. This means DB queries
# don't block the FastAPI event loop — same principle as the
# thread pool in yf_client, but cleaner because aiomysql is
# natively async rather than blocking in a thread.
#
# This requires adding aiomysql to requirements.txt.
# =============================================================

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text

from src.config import settings


# ── ENGINE ─────────────────────────────────────────────────────────────────────
# create_async_engine creates the connection pool.
# aiomysql is the async driver — note the +aiomysql in the URL scheme.
#
# pool_size=10      → keep 10 connections open and ready
# max_overflow=20   → allow up to 20 extra connections under heavy load
# pool_pre_ping=True → test each connection before use; if MariaDB
#                      restarted, the stale connection is discarded and
#                      a fresh one opened. Prevents "MySQL server has
#                      gone away" errors after idle periods.
# echo=False        → set to True temporarily to log every SQL statement
#                      (useful for debugging, too noisy for production)

engine = create_async_engine(
    settings.ASYNC_DATABASE_URL,
    pool_size       = 10,
    max_overflow    = 20,
    pool_pre_ping   = True,
    echo            = settings.APP_ENV == "development",
)


# ── SESSION FACTORY ────────────────────────────────────────────────────────────
# async_sessionmaker creates a reusable factory for AsyncSession objects.
#
# expire_on_commit=False → after a commit, ORM objects remain usable.
#                          Without this, accessing any attribute after
#                          commit() triggers a new DB query — confusing
#                          behaviour in async code where the session may
#                          already be closed.

AsyncSessionFactory = async_sessionmaker(
    bind            = engine,
    class_          = AsyncSession,
    expire_on_commit= False,
)


# ── FASTAPI DEPENDENCY ─────────────────────────────────────────────────────────
# get_db() is injected into route functions using FastAPI's Depends().
#
# Usage in a route:
#   async def my_route(db: AsyncSession = Depends(get_db)):
#       result = await db.execute(select(UserIdentity))
#
# The try/finally guarantees the session is closed even if the route
# raises an exception. The yield is what makes this a generator-based
# dependency — FastAPI runs everything after yield as cleanup.

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── LIFECYCLE FUNCTIONS ────────────────────────────────────────────────────────
# Called from main.py lifespan to set up and tear down the pool cleanly.

async def init_db() -> None:
    """
    Verify the database connection is alive at startup.
    Does NOT create tables — Alembic handles that.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("MariaDB connection pool initialised successfully")
    except Exception as e:
        logger.error(f"MariaDB connection failed at startup: {e}")
        raise   # Crash fast — better than silent failure


async def close_db() -> None:
    """
    Dispose the connection pool at shutdown.
    Closes all open connections cleanly.
    """
    await engine.dispose()
    logger.info("MariaDB connection pool closed")