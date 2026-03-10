# =============================================================
# src/core/redis_client.py
#
# Single shared Redis client for the whole application.
# Created once at startup, closed at shutdown.
# Both the scheduler and consumer import from here.
# =============================================================

import redis.asyncio as aioredis
from loguru import logger
from src.config import settings

# Module-level client — initialised in init_redis()
_redis_client: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    global _redis_client
    _redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding        = "utf-8",
        decode_responses = True,
    )
    # Verify connection
    await _redis_client.ping()
    logger.info(f"Redis connected: {settings.REDIS_URL}")
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        logger.info("Redis connection closed")


def get_redis() -> aioredis.Redis:
    """FastAPI dependency — returns the shared Redis client."""
    if not _redis_client:
        raise RuntimeError("Redis not initialised — call init_redis() first")
    return _redis_client