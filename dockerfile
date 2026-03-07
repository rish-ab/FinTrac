# =============================================================
# FinTrac V2 — Dockerfile
# Python 3.11 (matches requirements.txt)
# =============================================================

FROM python:3.11-slim-bookworm

WORKDIR /app

# System dependencies
# build-essential : compiles C extensions (pyarrow, cryptography)
# libgomp1        : OpenMP for torch / numpy parallelism
# curl            : healthcheck utility
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Layer 1: dependencies (cached unless requirements.txt changes) ──
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Layer 2: source code (changes frequently, goes last) ───────────
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini .

# Expose FastAPI port
EXPOSE 8000

# Healthcheck — hits FastAPI's /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]