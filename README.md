# FinTrac V3 — Self-Calibrating AI Investment Analyst

FinTrac is a local-first investment analysis platform. A local LLM (Mistral 7B via Ollama) reads live market data and SEC filings and returns a structured **BUY / HOLD / AVOID** verdict with a confidence score. Every verdict is recorded. Once its horizon passes, FinTrac grades it against the real price, and the results drive a feedback loop:

- **Calibration:** statistically corrects the model's confidence.
- **Prompt evolution:** adds rules learned from the model's own mistakes to future prompts.

All inference runs on your machine. No market data, portfolio or prompt is sent to a third-party AI provider.

```
 React UI ──► FastAPI ──► yfinance (prices, fundamentals)
                │   ├──► SEC EDGAR (10-K / 8-K) ──► ChromaDB (RAG)
                │   ├──► Ollama: mistral (verdicts) + nomic-embed-text (embeddings)
                │   ├──► MariaDB (users, portfolios, predictions, calibration)
                │   └──► Redis (price-alert stream)
                └── scheduler: evaluate → attribute → calibrate → evolve prompt
```

---

## Contents

1. [Technologies used](#1-technologies-used)
2. [Queries and math behind the analysis](#2-queries-and-math-behind-the-analysis)
3. [LLM inference, the learning loop and the RAG pipeline](#3-llm-inference-the-learning-loop-and-the-rag-pipeline)
4. [Installation](#4-installation)
5. [Using the app](#5-using-the-app)
6. [Project layout](#6-project-layout)
7. [Known limitations](#7-known-limitations)

---

## 1. Technologies used

| Layer | Technology | Role in FinTrac |
|---|---|---|
| **LLM runtime** | [Ollama](https://ollama.com) | Serves models locally over HTTP (`:11434`) |
| **Reasoning model** | `mistral` (7B) | Produces the JSON investment verdict (`temperature=0.1`, `num_ctx=4096`, `format="json"`) |
| **Embedding model** | `nomic-embed-text` | 768-dim vectors for filing chunks and queries |
| **LLM orchestration** | LangChain (`langchain-ollama`, `langchain-core`) | `OllamaLLM`, `OllamaEmbeddings`, `ChatPromptTemplate` |
| **Vector store** | ChromaDB (persistent, cosine HNSW) | Stores filing chunks at `data/lake/chroma_db` |
| **API** | FastAPI + Uvicorn, Pydantic v2 | REST API at `/api/v1/*`, OpenAPI docs at `/docs` |
| **Relational DB** | MariaDB 11.3 | Users, portfolios, watchlists, predictions, outcomes, calibration profiles, prompt patches |
| **ORM / migrations** | SQLAlchemy 2 (async, `aiomysql`) + Alembic (`pymysql`) | Schema and migrations in `migrations/versions` |
| **Cache / queue** | Redis 7.2 (Streams) | `fintrac:alerts` stream for price alerts |
| **Market data** | `yfinance` | Equities, ETFs, FX, bonds, commodities, crypto, indices |
| **Filings** | SEC EDGAR REST API (`httpx`) | 10-K and 8-K text, no API key needed |
| **News events** | `feedparser` (Yahoo Finance, Investing.com RSS) | Market events used for outcome attribution |
| **Auth** | `python-jose` (JWT), `passlib[bcrypt]` | OAuth2 password flow |
| **Frontend** | React 18, TypeScript 5.6, Vite 5, Tailwind CSS 3, Recharts, lucide-react | Single-page app with light and dark themes |
| **Containers** | Docker + Docker Compose | `mariadb`, `redis`, `fintrac` (API) |
| **Testing** | pytest, pytest-asyncio | Calibration math, grading, dashboard buckets, job runner |

> `requirements.txt` also lists `duckdb`, `transformers`/`torch` (FinBERT), `sentence-transformers` and `fredapi`. These belong to earlier versions and are **not used by the current code path**. They make the Docker image larger but do no harm.

---

## 2. Queries and math behind the analysis

### 2.1 The evaluation request

`POST /api/v1/analysis/evaluate`

```json
{ "ticker": "AAPL", "budget": 10000, "horizon_years": 1, "risk_tolerance": "moderate", "question": "Is now a good entry?" }
```

FastAPI runs two things concurrently:

1. **Market snapshot** (`yf_client_v2.fetch_market_snapshot`). The ticker is resolved through `asset_registry.resolve_ticker`, so `USDCHF`, `GOLD` and `BTC` map to Yahoo symbols such as `USDCHF=X`, `GC=F` and `BTC-USD`. The snapshot is then built from `yf.Ticker(...).info`:
   price, market cap, trailing and forward P/E, P/B, beta, dividend yield, 52-week high and low, average volume and analyst target.
   Non-equity classes get class-appropriate fields. For example, FX has no P/E, and its sector is set to `"Foreign Exchange"`.
2. **Budget projection** (`calculate_budget_projection`), described below.

### 2.2 Budget projection (historical CAGR)

Lookback window: $L = \min(\max(H, 0.5),\ 5)$ years, where $H$ is the requested horizon.

$$
\text{years}_{\text{actual}} = \frac{N_{\text{trading days}}}{252}
\qquad
\text{CAGR} = \left(\frac{P_{\text{end}}}{P_{\text{start}}}\right)^{1/\text{years}_{\text{actual}}} - 1
$$

The CAGR is clamped per asset class: FX to ±5%, bonds to −2% … +8%, and crypto to −80% … +200%.

$$
V_{\text{mid}} = B\,(1+\text{CAGR})^{H}, \qquad
V_{\text{low}} = V_{\text{mid}}\cdot m_{\text{low}}, \qquad
V_{\text{high}} = V_{\text{mid}}\cdot m_{\text{high}}
$$

| Asset class | $m_{\text{low}}$ | $m_{\text{high}}$ |
|---|---|---|
| Equity | 0.50 | 2.0 |
| Index | 0.60 | 1.8 |
| Commodity | 0.60 | 1.8 |
| Bond | 0.95 | 1.08 |
| Forex | 0.90 | 1.10 |
| Crypto | 0.20 | 5.0 |

The projection goes into the LLM prompt as context. It is not a forecast the system is graded on.

### 2.3 Recording the prediction

Every verdict is saved as a `prediction_record` row. It stores the direction, the confidence shown to the user, `raw_confidence` (the model's output before correction), the sector, the asset class and the prompt version. It also stores the entry price in `analysis_context.market_price` and sets `evaluation_due_at = now + horizon`.

`horizon_years` maps to the horizon label as follows:

| `horizon_years` | `< 0.12` | `< 0.38` | `< 0.75` | otherwise |
|---|---|---|---|---|
| label | `1m` | `3m` | `6m` | `round(years)y` |

### 2.4 Grading a prediction (`prediction_evaluator.py`, every 24 h)

The price is fetched **as of `evaluation_due_at`**, using the last close on or before that date. It is not "today's" price, so an evaluator that runs late doesn't change the result.

$$
r = \frac{P_{\text{horizon}} - P_{\text{entry}}}{P_{\text{entry}}}\times 100
$$

| Verdict | Counted as correct when |
|---|---|
| BUY | $r > 0$ |
| AVOID | $r < 0$ |
| HOLD | $\lvert r\rvert \le 3\%$ (the `HOLD_TOLERANCE_PCT` band) |

Predictions younger than 24 h are never graded, even if marked as due. The backtester uses the same `grade_direction` function, so live accuracy and backtest accuracy are directly comparable.

Selection query:

```sql
SELECT * FROM prediction_record
WHERE evaluation_due_at <= NOW() AND evaluation_status = 'PENDING'
ORDER BY evaluation_due_at;
```

### 2.5 Calibration math (`calibration_metrics.py`, `calibration_engine.py`, every 7 days)

**Data hygiene**

- **De-duplication:** only one prediction per `(ticker, day, horizon, direction)` is kept. A repeated query would otherwise count the same outcome several times.
- **Calibration uses `raw_confidence`:** using the corrected values would make the engine learn from its own corrections.
- **Temporal split:** the oldest 70% of predictions are used for fitting and the newest 30% are held out.

**Wilson score interval (95%, z = 1.96).** Every rate is tested with this interval, so a bias is only flagged when the *whole* interval is on the wrong side of the threshold.

$$
\hat p = \frac{k}{n},\quad
\text{centre} = \frac{\hat p + \frac{z^2}{2n}}{1+\frac{z^2}{n}},\quad
\text{half} = \frac{z}{1+\frac{z^2}{n}}\sqrt{\frac{\hat p(1-\hat p)}{n} + \frac{z^2}{4n^2}}
$$

**Brier score.** Lower is better. Validation uses it to accept or reject each correction.

$$
\text{Brier} = \frac{1}{n}\sum_{i=1}^{n}(c_i - y_i)^2,\qquad y_i\in\{0,1\}
$$

**Expected Calibration Error.** Predictions are grouped into 10 equal-width confidence buckets $B_b$.

$$
\text{ECE} = \sum_{b}\frac{|B_b|}{n}\,\bigl|\text{acc}(B_b) - \overline{\text{conf}}(B_b)\bigr|
$$

**Bias detectors.** Each needs $n \ge 10$. A bias is only *activated* if its correction lowers the Brier score on the 30% holdout.

| Bias | Fires when | Correction factor |
|---|---|---|
| `OPTIMISM_BIAS` | BUY share > 65% **and** the upper Wilson bound of BUY precision < 0.5 | $\max(0.7,\ 1 - 0.5\,(s_{\text{buy}}-0.5))$ |
| `PESSIMISM_BIAS` | AVOID share > 65% **and** the upper bound of AVOID precision < 0.5 | $\max(0.7,\ 1 - 0.5\,(s_{\text{avoid}}-0.5))$ |
| `OVERCONFIDENCE` | Upper bound of accuracy < mean confidence | $\text{clip}\bigl(\tfrac{\text{acc}}{\overline{c}},\,0.5,\,1\bigr)$ |
| `VOLATILITY_UNDERESTIMATION` | mean $\lvert r\rvert$ > 10% **and** upper bound of accuracy < 0.55 | $\max(0.6,\ 1 - 0.3\cdot\overline{\lvert r\rvert}/100)$ |
| `DIRECTION_BIAS` | Lower Wilson bound of the BUY or AVOID share > 0.80 | $\max(0.7,\ 1 - 0.4\,(s-0.5))$ |
| `CONFIDENCE_MAP` | $n \ge 30$ and isotonic map improves holdout Brier | isotonic map (below) |

**Isotonic regression (pool-adjacent-violators).** This learns a monotone map from raw confidence to observed hit rate. Unlike a single scaling factor, it can fix overconfidence at the top and underconfidence at the bottom at the same time, while keeping the model's ranking of its own calls. Tied confidences (LLMs like round numbers such as 0.7) are pooled first. At inference time the map is applied by piecewise-linear interpolation, and is flat beyond its end points.

**Scopes.** Profiles are fitted for global, per sector and per asset class. At inference time only the **most specific** scope that has profiles is used (sector > asset class > global):

$$
c_{\text{shown}} =
\begin{cases}
\text{isotonic}(c_{\text{raw}}) & \text{if a CONFIDENCE\_MAP is active}\\[2pt]
c_{\text{raw}}\cdot\min_j f_j & \text{otherwise}
\end{cases}
\qquad\text{clamped to }[0.1,\ 1.0]
$$

### 2.6 Prompt-evolution queries (`prompt_evolver.py`, after calibration)

The detectors are SQL aggregations over `prediction_record ⨝ prediction_outcome`:

```sql
-- Sector weakness: sector accuracy ≥ 15 pts below global → sector_guidance patch
SELECT pr.sector, COUNT(pr.id) AS total, SUM(po.is_direction_correct) AS correct,
       AVG(pr.confidence_score) AS avg_confidence
FROM prediction_record pr JOIN prediction_outcome po ON pr.id = po.prediction_id
WHERE pr.evaluation_status = 'EVALUATED'
GROUP BY pr.sector HAVING COUNT(pr.id) >= 5;

-- Direction pattern: one direction > 70% of calls and < 55% accurate → direction_guard patch
SELECT pr.predicted_direction, COUNT(pr.id), SUM(po.is_direction_correct)
FROM prediction_record pr JOIN prediction_outcome po ON pr.id = po.prediction_id
WHERE pr.evaluation_status = 'EVALUATED'
GROUP BY pr.predicted_direction;

-- Risk blind spots: confident (≥ 0.75) but wrong, worst first → risk_emphasis patch
SELECT pr.*, po.* FROM prediction_record pr JOIN prediction_outcome po ON pr.id = po.prediction_id
WHERE pr.evaluation_status = 'EVALUATED' AND pr.confidence_score >= 0.75
  AND po.is_direction_correct = 0
ORDER BY po.absolute_error DESC LIMIT 20;
```

`confidence_anchor` patches fire when predictions with confidence ≥ 0.8 are less than 55% accurate (minimum 5 samples).

### 2.7 Outcome attribution (`attribution_engine.py`, every 24 h)

Market events are pulled from RSS feeds by `scripts/ingest_events.py`. Each event gets a keyword-based type and a sentiment score:

$$
s = \frac{\#\text{positive words} - \#\text{negative words}}{\#\text{positive} + \#\text{negative}} \in [-1, 1]
$$

For each evaluated prediction, events are selected that match the ticker, the sector or "major" event types, and fall inside $[t_{\text{pred}} - 7\text{d},\ t_{\text{eval}} + 1\text{d}]$. Each event is then scored:

$$
\text{score} = 0.4\cdot\text{temporal} + 0.4\cdot\text{sentiment alignment} + 0.2\cdot\text{importance}
$$

- **Temporal:** 1.0 for events in the last 20% of the horizon, 0.8 for the middle part and 0.5 early on. Events before the prediction decay linearly to 0 at −30 days, at half weight.
- **Sentiment alignment:** $\lvert s\rvert$ when the event supports the right outcome or contradicts the wrong one. Otherwise it is 0.3.
- **Importance:** EARNINGS 1.0, FED 0.9, M&A 0.85, LEADERSHIP 0.7, LEGAL 0.65, PRODUCT 0.6, GENERAL 0.3.

Attributions are stored only if the score is ≥ 0.3.

### 2.8 Backtesting (`backtester.py`)

For each date $d$ from `start_date` to `end_date`, stepping by `interval_days` (maximum 24 points):

1. Take the last close on or before $d$ as the entry price.
2. Ask the LLM for a verdict, with **calibration disabled** so no outcome learned after $d$ can leak into the prediction.
3. Take the close at $d + \text{horizon}$ as the exit price, and grade it with `grade_direction`.

$$
\text{accuracy} = \frac{\#\text{correct}}{\#\text{graded}}\times 100
$$

`POST /api/v1/analysis/backtest-range/jobs` runs this in the background. Poll `GET /api/v1/jobs/{id}` for progress and partial rows, and use `POST /api/v1/jobs/{id}/cancel` to stop it.

### 2.9 Dashboard queries (`routes/dashboard.py`)

```sql
-- Accuracy by sector
SELECT pr.sector, COUNT(pr.id) AS total, SUM(po.is_direction_correct) AS correct
FROM prediction_record pr JOIN prediction_outcome po ON pr.id = po.prediction_id
WHERE pr.evaluation_status = 'EVALUATED'
GROUP BY pr.sector ORDER BY correct DESC;

-- Daily timeline (last N days, includes still-pending predictions)
SELECT DATE(pr.prediction_timestamp) AS date, COUNT(pr.id) AS total,
       SUM(po.is_direction_correct) AS correct
FROM prediction_record pr LEFT JOIN prediction_outcome po ON pr.id = po.prediction_id
WHERE pr.prediction_timestamp >= :start
GROUP BY DATE(pr.prediction_timestamp) ORDER BY date;
```

The confidence-calibration chart buckets shown confidence into `0.0-0.5, 0.5-0.6, …, 0.9-1.0`, and gives accuracy for each bucket. `/calibration-metrics` returns the full report: Brier and ECE for raw vs. shown confidence, a reliability table with Wilson intervals, per-action hit rates, per-horizon hit rates and the "always BUY" baseline (the share of predictions where the price simply went up).

### 2.10 Price alerts (`alert_monitor.py`, every 60 s)

For each watchlist item:

- If `price ≥ price_trigger_high`, a `PRICE_HIGH` alert fires.
- If `price ≤ price_trigger_low`, a `PRICE_LOW` alert fires.

Each alert is written to `alert_queue` (MariaDB, the record of truth) and published to the Redis stream `fintrac:alerts` for delivery. A new alert isn't created while an undelivered one of the same type is still pending.

---

## 3. LLM inference, the learning loop and the RAG pipeline

### 3.1 Is the LLM trained?

**No weights are trained or fine-tuned.** FinTrac uses the stock `mistral` model through Ollama. The system "learns" at inference time, in three ways that don't touch the weights:

| Mechanism | What changes | Where |
|---|---|---|
| **RAG** | What the model *knows*: current filing text is added to the prompt | `agent/rag_pipeline.py` |
| **Calibration** | What the user *sees*: raw confidence is corrected statistically after the model answers | `engine/calibration_engine.py` |
| **Prompt evolution** | How the model *reasons*: rules learned from past failures are added to the prompt | `engine/prompt_evolver.py` |

This is a closed feedback loop driven by real outcomes:

```
 predict ──► record (raw_confidence, prompt_version)
    ▲                         │ horizon elapses
    │                         ▼
 inject rules +        evaluate vs. real price (24h job)
 correct confidence           │
    ▲                         ▼
 prompt patches ◄── calibration profiles ◄── attribution
  (7-day job)           (7-day job)          (24h job)
```

### 3.2 Inference path (`advisor_agent.get_investment_verdict`)

1. **Load calibration profiles** for the asset's sector and asset class, plus global ones. Behavioural biases become a `CALIBRATION WARNINGS` block in the prompt. The numeric map is applied later.
2. **Load active prompt patches.** They become a `LEARNED IMPROVEMENTS` block, and the prompt version becomes `v1.0.0+{n}patches`.
3. **RAG retrieval:** the top 2 filing passages for this ticker (see 3.4).
4. **Build the prompt** from `INVESTMENT_PROMPT` in `agent/prompts.py`. It has a system message requiring a single JSON object with `action`, `confidence`, `reasoning`, `risk_flags`, `alternatives` and `data_gaps`. The human message contains the user's intent, the live market data, the budget projection, the calibration warnings, the learned rules and the filing excerpts.
5. **Invoke** `OllamaLLM(model=mistral, temperature=0.1, num_ctx=4096, format="json")` in a thread pool, so the event loop isn't blocked.
6. **Parse:** strip any code fences, run `json.loads`, and validate into the `InvestmentVerdict` Pydantic model.
7. **Correct confidence:** save `raw_confidence`, then apply the isotonic map or scaling factor.
8. **Return** the verdict. The prediction is recorded and SEC filings for the ticker are fetched in background tasks.

Low temperature, JSON mode and a short context are deliberate. A 7B model follows instructions noticeably worse when the prompt is long, which is also why RAG excerpts are trimmed.

### 3.3 Prompt patch lifecycle

```
proposed ──(≥ 24 h)──► testing ──(≥ 5 graded predictions)──► active
                                     │
                                     └─ accuracy drop > 5 pts ──► retired
```

A newer patch of the same type and scope retires the older one. You can trigger a run manually with `POST /api/v1/trigger-evolution`.

### 3.4 RAG pipeline

**Ingestion** (`sec_client.py`, `document_ingester.py`). After every evaluation, a background task fetches filings for that ticker:

1. Map the ticker to its CIK via `https://www.sec.gov/files/company_tickers.json`.
2. List filings via `https://data.sec.gov/submissions/CIK##########.json`, keeping 10-K and 8-K (up to 3).
3. Download the primary document, strip HTML and iXBRL tags and boilerplate, collapse whitespace and truncate to 50,000 characters.
4. Save to `data/lake/documents/{TICKER}/{FORM}/{accession}.txt` and register it in `document_registry` with status `PENDING`. A SHA-256 content hash prevents duplicates.

**Embedding** runs in the background at startup, with a 180 s timeout per document:

- **Chunking:** 300-word windows with a 30-word overlap, so a sentence on a boundary always appears whole in at least one chunk. Chunks shorter than 100 characters are dropped.
- **Embedding:** `nomic-embed-text` via `OllamaEmbeddings.embed_documents`, producing 768-dimensional vectors.
- **Storage:** `chromadb.PersistentClient("data/lake/chroma_db")`, collection `fintrac_documents`, `hnsw:space = cosine`. Each chunk is upserted with the metadata `{document_id, ticker, doc_type, filed_at, chunk_index, chunk_total}`. ChromaDB telemetry is turned off.
- The document is marked `DONE`, or `FAILED` with a reason.

**Retrieval:**

```python
q = embeddings.embed_query(user_question or f"{ticker} financial risks outlook revenue")
collection.query(query_embeddings=[q], n_results=2, where={"ticker": ticker})
```

- The `where` filter keeps one company's filings out of another's analysis.
- Cosine distance $d \in [0, 2]$ is reported as similarity $1 - d/2$.
- The top 2 passages are trimmed to 300 characters each and added to the prompt under `=== RELEVANT FILING EXCERPTS ===`.

### 3.5 Swapping in a different model

- **Another Ollama model:** `ollama pull llama3.1`, then set `OLLAMA_MODEL=llama3.1` in `.env` and restart the API.
- **A hosted model** (for example Anthropic): replace the `llm = OllamaLLM(...)` instance in `src/agent/advisor_agent.py` with a LangChain chat model, and add its package to `requirements.txt`. This sends prompts to an external provider, so you lose the local-only privacy guarantee.

If you change models, the existing calibration profiles describe the old model. Consider resetting them, or comparing results by `model_version`.

---

## 4. Installation

Tested on Linux (Ubuntu/Debian). macOS and Windows (WSL2) use the same steps with their own package installers.

### 4.1 Hardware

| | Minimum | Recommended |
|---|---|---|
| RAM | 8 GB | 16 GB+ |
| Disk | 15 GB free (Docker images, about 4 GB of models, data) | 25 GB |
| GPU | Not required, since Ollama runs on CPU | An NVIDIA or Apple Silicon GPU makes verdicts several times faster |

### 4.2 Install the required software

#### Git

```bash
sudo apt update && sudo apt install -y git curl
```

#### Docker Engine + Compose plugin

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER      # then log out and back in
docker --version && docker compose version
```

On macOS or Windows, install [Docker Desktop](https://www.docker.com/products/docker-desktop/) instead.

#### Node.js 20 LTS + npm (for the frontend)

With **nvm** (recommended):

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install 20
node -v && npm -v                  # Node ≥ 18 is required, 20+ recommended
```

Alternatively, use the NodeSource packages: `curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs`. On macOS, use `brew install node@20`.

#### Ollama (local LLM runtime)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama --version
```

On macOS or Windows, download the installer from <https://ollama.com/download>.

**Let the Docker container reach Ollama.** The API runs in Docker and calls Ollama on the host at `http://host.docker.internal:11434`. On Linux, Ollama listens only on `127.0.0.1` by default, so you need to make it listen on all interfaces:

```bash
sudo systemctl edit ollama
# add these lines in the editor, then save:
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"

sudo systemctl daemon-reload && sudo systemctl restart ollama
```

If port 11434 is reachable from outside your machine, block it with your firewall. Docker Desktop on macOS and Windows doesn't need this step.

#### Pull the models

```bash
ollama pull mistral            # reasoning model, ~4.1 GB
ollama pull nomic-embed-text   # embedding model, ~274 MB
ollama list                    # both should be listed
ollama run mistral "Reply with OK"   # quick smoke test
```

#### Python 3.11 (optional)

You only need Python on the host to run the tests or the backend outside Docker.

```bash
sudo apt install -y python3.11 python3.11-venv
```

### 4.3 Clone and configure

```bash
git clone https://github.com/rish-ab/FinTrac.git
cd FinTrac
```

Create `.env` in the project root. Docker Compose and the API both read it.

```dotenv
# ── Ollama ──────────────────────────────
OLLAMA_MODEL=mistral
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_BASE_URL=http://host.docker.internal:11434

# ── MariaDB (used by docker-compose and the API) ──
DB_ROOT_PASSWORD=change-me-root
DB_NAME=fintrac
DB_USER=fintrac_user
DB_PASSWORD=change-me
DB_HOST=mariadb
DB_PORT=3306

# ── Redis ───────────────────────────────
REDIS_URL=redis://redis:6379/0

# ── App ─────────────────────────────────
JWT_SECRET_KEY=replace-with-output-of-openssl-rand-hex-32
APP_ENV=development
LOG_LEVEL=INFO
```

Generate a JWT secret with `openssl rand -hex 32`. Never commit `.env`.

### 4.4 Start the backend

```bash
docker compose up --build -d       # builds the API image, starts mariadb, redis and fintrac
docker compose ps                  # mariadb and redis should be "healthy"
```

Create the database schema. This only needs doing on the first run, and again after pulling new migrations.

```bash
docker exec -it fintrac_api alembic upgrade head
docker compose restart fintrac
```

Verify:

```bash
curl http://localhost:8000/health
docker logs -f fintrac_api        # look for "Ollama reachable — model: mistral"
```

The interactive API docs are at <http://localhost:8000/docs>.

### 4.5 Start the frontend

```bash
cd frontend
cp .env.example .env               # defaults proxy /api to http://localhost:8000
npm install
npm run dev
```

Open the URL Vite prints, normally <http://localhost:5173>.

Production build:

```bash
npm run typecheck && npm run build && npm run preview
```

### 4.6 Optional: seed data and tests

```bash
# Pull recent market news events (used by outcome attribution)
docker exec -it fintrac_api python scripts/ingest_events.py

# Generate a spread of predictions across sectors (calls the AI many times, so it's slow)
docker exec -it fintrac_api python scripts/build_dataset.py

# Unit tests (on the host, in a venv)
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

### 4.7 Running the backend without Docker (optional)

Keep MariaDB and Redis in Docker (`docker compose up -d mariadb redis`) and run the API on the host:

```bash
source .venv/bin/activate
export DB_HOST=127.0.0.1 REDIS_URL=redis://127.0.0.1:6379/0 OLLAMA_BASE_URL=http://127.0.0.1:11434
alembic upgrade head
uvicorn src.main:app --reload --port 8000
```

### 4.8 Troubleshooting

| Symptom | Fix |
|---|---|
| `Ollama not reachable` in the API logs | Check `curl http://localhost:11434/api/tags` on the host, and make sure `OLLAMA_HOST=0.0.0.0` is set (Linux; see 4.2) |
| Verdicts are slow (30–120 s) | Expected on CPU. Use a GPU, or try a smaller model such as `phi3:mini` |
| `MariaDB connection failed at startup` | Wait for `mariadb` to show as healthy, then `docker compose restart fintrac` |
| `Table ... doesn't exist` | Run `docker exec -it fintrac_api alembic upgrade head` |
| The frontend shows network errors | Check the API is on `:8000`, or set `VITE_API_PROXY_TARGET` in `frontend/.env` |
| Calibration shows "not enough data" | Calibration needs at least 10 graded predictions per scope, and 30 for the isotonic map. Predictions are graded only after their horizon |
| Reset everything | `docker compose down -v` deletes the DB and Redis volumes, and `rm -rf data/lake/chroma_db` clears the vector store |

---

## 5. Using the app

1. **Register or sign in** from the top bar.
2. **Analyze:** pick an asset (equity, ETF, FX, bond, commodity, crypto or index), set a budget and horizon, and get a verdict with reasoning, risk flags and alternatives.
3. **Backtesting:** run a single date, or a date range as a background job with live progress and a Cancel button.
4. **Calibration:** see accuracy by sector, the reliability diagram, Brier score and ECE for raw vs. shown confidence, and active bias profiles. You can trigger a run manually.
5. **Prompt evolution:** see the lifecycle of the learned patches.
6. **Portfolio and watchlist:** track assets and set high and low price alerts.

---

## 6. Project layout

```
src/
  main.py                 FastAPI app, startup tasks (embedding, scheduler, alert consumer)
  config.py               Settings loaded from .env
  agent/
    advisor_agent.py      LLM inference, calibration + patch injection, JSON parsing
    prompts.py            System and investment/comparison prompt templates
    rag_pipeline.py       Chunking, embedding, ChromaDB storage and retrieval
  engine/
    prediction_evaluator.py  Grades predictions at their horizon
    calibration_metrics.py   Wilson, Brier, ECE, isotonic regression (pure functions)
    calibration_engine.py    Bias detection, holdout validation, confidence correction
    prompt_evolver.py        Failure-pattern detection and patch lifecycle
    attribution_engine.py    Links news events to outcomes
    backtester.py            Historical single-date and range backtests
    job_runner.py            In-process background jobs with progress and cancel
    scheduler.py             60 s / 24 h / 7 d task loop
    alert_monitor.py, alert_consumer.py   Price alerts via Redis Streams
  ingestion/              yfinance, SEC EDGAR, RSS events, asset registry, ticker search
  api/routes/             analysis, assets, auth, portfolios, alerts, dashboard, jobs
  db/                     SQLAlchemy models (models.py, v3_models.py), session
migrations/               Alembic migrations
frontend/                 React + Vite + Tailwind SPA
tests/                    pytest suite
scripts/                  Dataset builder, event ingestion, attribution runner
data/lake/                Filing text and the ChromaDB index (created at runtime)
```

---

## 7. Known limitations

- **Backtests are an optimistic upper bound.** The LLM's training data may include what happened after the backtest date, and RAG uses current filings rather than filings from that date.
- **Event sentiment is keyword-based**, not model-based.
- **Calibration needs volume.** With few graded predictions, the statistical gates (correctly) refuse to flag biases.
- **This is not financial advice.** FinTrac is a research and learning project.

## License

See [LICENSE](LICENSE).
