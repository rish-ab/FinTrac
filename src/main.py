# =============================================================
# src/main.py
# =============================================================

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import analysis


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

    # TODO: warm up ChromaDB
    # from src.agent.rag_pipeline import init_vector_store
    # await init_vector_store()

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


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "2.0.0"}