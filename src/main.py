# =============================================================
# src/main.py
# =============================================================

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import analysis, auth, portfolio, alerts
from src.api.routes import dashboard
from src.api.routes import assets

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ───────────────────────────────────────────────
    print("FinTrac starting up...")

    # MariaDB
    from src.db.session import init_db, close_db
    await init_db()

    # Redis
    from src.core.redis_client import init_redis, close_redis
    redis_client = await init_redis()

    # Ollama
    from src.agent.advisor_agent import ping_ollama
    await ping_ollama()

    # ChromaDB - initialize collection only (fast, no embedding)
    from src.agent.rag_pipeline import init_chroma_collection
    init_chroma_collection()

    # Start background document embedding (non-blocking)
    # Runs in background, won't block startup if Ollama is slow
    from src.agent.rag_pipeline import background_embed_pending_documents
    from src.db.session import AsyncSessionFactory
    
    async def _run_background_embedding():
        """Background task: process pending document embeddings"""
        try:
            # Wait 5 seconds to let server start fully
            await asyncio.sleep(5)
            async with AsyncSessionFactory() as bg_session:
                await background_embed_pending_documents(bg_session, batch_size=10)
        except Exception as e:
            print(f"Background embedding error: {e}")
    
    embedding_task = asyncio.create_task(_run_background_embedding())

    # Start alert consumer (reads Redis Stream, marks alerts delivered)
    from src.engine.alert_consumer import run_consumer
    consumer_task = asyncio.create_task(run_consumer(redis_client))

    # Start scheduler (runs alert monitor every 60s)
    from src.engine.scheduler import run_scheduler
    scheduler_task = asyncio.create_task(run_scheduler(redis_client))

    print("FinTrac ready.")
    yield

    # ── SHUTDOWN ──────────────────────────────────────────────
    consumer_task.cancel()
    scheduler_task.cancel()
    embedding_task.cancel()
    await close_db()
    await close_redis()
    print("FinTrac shutdown complete.")


app = FastAPI(
    title       = "FinTrac API",
    description = "AI-powered financial tracking and investment analysis.",
    version     = "2.0.0",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
    ],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.include_router(analysis.router,  prefix="/api/v1/analysis",   tags=["Analysis"])
app.include_router(auth.router,      prefix="/api/v1/auth",        tags=["Auth"])
app.include_router(portfolio.router, prefix="/api/v1/portfolios",  tags=["Portfolios"])
app.include_router(alerts.router,    prefix="/api/v1/alerts",      tags=["Alerts"])
app.include_router(dashboard.router, prefix="/api/v1")  
app.include_router(assets.router, prefix="/api/v1")

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "2.0.0"}