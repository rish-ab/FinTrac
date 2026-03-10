# =============================================================
# src/main.py
# =============================================================

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import analysis
from src.api.routes import auth
from src.api.routes import portfolio


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ───────────────────────────────────────────────
    print("FinTrac starting up...")

    # Verify MariaDB is reachable
    from src.db.session import init_db
    await init_db()

    # Ping Ollama
    from src.agent.advisor_agent import ping_ollama
    await ping_ollama()

    # Initialise ChromaDB and process any pending documents from last session
    from src.agent.rag_pipeline import init_vector_store
    from src.db.session import AsyncSessionFactory
    async with AsyncSessionFactory() as startup_session:
        await init_vector_store(startup_session)

    print("FinTrac ready.")
    yield

    # ── SHUTDOWN ──────────────────────────────────────────────
    from src.db.session import close_db
    await close_db()
    print("FinTrac shutdown complete.")


app = FastAPI(
    title="FinTrac API",
    description="AI-powered financial tracking and investment analysis.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    analysis.router,
    prefix="/api/v1/analysis",
    tags=["Analysis"],
)

app.include_router(
    auth.router,
    prefix="/api/v1/auth",
    tags=["Auth"],
)

app.include_router(
    portfolio.router,
    prefix="/api/v1/portfolios",
    tags=["Portfolios"],
)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "2.0.0"}