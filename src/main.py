# =============================================================
# src/main.py
# The entry point of the entire FinTrac backend.
# This is the file uvicorn runs: "uvicorn src.main:app"
# =============================================================

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import analysis


# ── LIFESPAN ──────────────────────────────────────────────────────────────────
# asynccontextmanager turns this function into a context manager FastAPI
# understands. Everything BEFORE yield runs on startup. Everything AFTER
# yield runs on shutdown. This replaces the old @app.on_event("startup")
# pattern which is now deprecated in FastAPI.
#
# Why does this matter for FinTrac?
# On startup we need to:
#   - Confirm the DB connection is alive before accepting requests
#   - Warm up the ChromaDB vector store (loading embeddings into memory)
#   - Confirm Ollama is reachable
# On shutdown we need to:
#   - Close DB connection pools cleanly (prevents "too many connections" errors
#     on the next boot)
#
# We leave those connections as TODO stubs for now — the important thing is
# the pattern is in place so we plug them in naturally as we build each layer.

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ───────────────────────────────────────────────
    print("FinTrac starting up...")

    # Ping Ollama — if unreachable, app still starts but verdicts return null
    from src.agent.advisor_agent import ping_ollama
    await ping_ollama()

    # TODO: initialise SQLAlchemy engine
    # from src.db.session import init_db
    # await init_db()

    # TODO: warm up ChromaDB collection
    # from src.agent.rag_pipeline import init_vector_store
    # await init_vector_store()

    print("FinTrac ready.")

    yield   # ← application runs here

    # ── SHUTDOWN ──────────────────────────────────────────────
    print("FinTrac shutting down...")

    # TODO: dispose SQLAlchemy engine
    # from src.db.session import close_db
    # await close_db()

    print("FinTrac shutdown complete.")


# ── APP INSTANCE ───────────────────────────────────────────────────────────────
# This object is what uvicorn imports. Every route, middleware, and plugin
# attaches to it. The lifespan argument wires up our startup/shutdown hooks.

app = FastAPI(
    title="FinTrac API",
    description="AI-powered financial tracking and investment analysis.",
    version="2.0.0",
    lifespan=lifespan,
)


# ── CORS MIDDLEWARE ────────────────────────────────────────────────────────────
# CORS (Cross-Origin Resource Sharing) is a browser security rule.
# By default, a browser will refuse to let a frontend at http://localhost:3000
# call an API at http://localhost:8000 because they're on different "origins"
# (different ports count as different origins).
#
# This middleware tells the browser: "it is safe to call this API from these
# origins." In development we allow localhost on common frontend ports.
# In production this list would be locked down to your actual domain.
#
# allow_credentials=True   → allows cookies/auth headers to be sent
# allow_methods=["*"]      → allows GET, POST, PUT, DELETE, etc.
# allow_headers=["*"]      → allows any request headers (e.g. Authorization)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",    # React / Next.js default
        "http://localhost:5173",    # Vite default
        "http://localhost:8080",    # Vue CLI default
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── ROUTERS ────────────────────────────────────────────────────────────────────
# Instead of defining every route in this file (which would become unreadable),
# FastAPI uses "routers" — separate files that group related routes, which we
# then "include" here with a URL prefix.
#
# prefix="/api/v1/analysis" means every route defined in the analysis router
# will be reachable at /api/v1/analysis/... — e.g. /api/v1/analysis/evaluate
#
# tags=["Analysis"] groups these routes together in the auto-generated
# API docs at http://localhost:8000/docs

app.include_router(
    analysis.router,
    prefix="/api/v1/analysis",
    tags=["Analysis"],
)

# TODO: add these routers as we build each layer
# app.include_router(portfolio.router, prefix="/api/v1/portfolio", tags=["Portfolio"])
# app.include_router(watchlist.router, prefix="/api/v1/watchlist", tags=["Watchlist"])
# app.include_router(auth.router,      prefix="/api/v1/auth",      tags=["Auth"])


# ── HEALTH ENDPOINT ────────────────────────────────────────────────────────────
# This is the endpoint the Docker HEALTHCHECK polls every 30 seconds.
# It intentionally lives in main.py, not in a router, because it checks
# whether the app itself is alive — not whether a feature works.
#
# A real health check would also query the DB and Redis. We expand it
# as we add those connections.

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "2.0.0"}