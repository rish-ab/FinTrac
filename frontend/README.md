# FinTrac V3 Frontend

React + Vite + TypeScript + Tailwind CSS frontend for the supplied FinTrac FastAPI OpenAPI contract. The application intentionally avoids fabricated market data, invented REST routes, or unsupported actions.

## Requirements

- Node.js 18+ (20+ recommended)
- npm
- Existing FinTrac FastAPI backend

## Run locally

```bash
cp .env.example .env
npm install
npm run dev
```

The Vite development proxy forwards `/api/*` and `/health` to `http://localhost:8000` by default. Set `VITE_API_PROXY_TARGET` to the backend origin if needed. Alternatively set `VITE_API_BASE_URL` to an explicit API origin and ensure the backend's CORS policy permits the frontend origin.

## Build and typecheck

```bash
npm run typecheck
npm run build
npm run preview
```

## Authentication

- Sign in submits `application/x-www-form-urlencoded` fields `grant_type=password`, `username`, `password`, and `scope` to the documented `/api/v1/auth/token` endpoint.
- The returned access token is stored in browser local storage and attached as a bearer token when present.
- User-specific portfolio and watchlist views request data only when a user is signed in.
- Registration uses `POST /api/v1/auth/register`.
- This is a browser frontend; use HTTPS in production and configure API CORS/security appropriately. For stronger token security, consider moving token handling into an existing secure server-side session architecture if your deployment supports it.

## API client

All HTTP calls live in `src/api/client.ts`. Type definitions derived from supplied schema details live in `src/api/types.ts`. Endpoints whose OpenAPI response schema is an untyped generic object intentionally use `Record<string, unknown>` rather than guessed fields. API errors preserve status and detail for screen-specific handling.

### Covered documented endpoints

- `GET /health`
- Auth: `POST /api/v1/auth/register`, `POST /api/v1/auth/token`, `GET /api/v1/auth/me`
- Analysis: `POST /api/v1/analysis/evaluate`, `GET /api/v1/analysis/snapshot`, `POST /api/v1/analysis/compare`, `POST /api/v1/analysis/backtest`, `POST /api/v1/analysis/backtest-range`
- Assets: `GET /api/v1/assets/search`, `/registry`, `/list`, `/examples`
- Dashboard: `/metrics`, `/accuracy-by-sector`, `/confidence-calibration`, `/recent-predictions`, `/top-attributions`, `/timeline`, `/calibration-profiles`, `/calibration-summary`, `POST /trigger-calibration`, `/model-improvements`, `/improvement-summary`, `POST /trigger-evolution`
- Portfolios: list/create/get/delete portfolio; list/add/remove watchlist item
- Alerts: `GET /api/v1/alerts/`

The wrappers use only the route paths and HTTP methods in the supplied specification. The client does not add assumed prediction, evaluation, position, trade, prompt-transition, or model-leaderboard endpoints.

## Screen implementation notes

- **Dashboard:** dynamically reads the `metrics`, `recent-predictions`, `timeline`, and calibration-summary responses. Generic metric keys and record columns are displayed from the actual payload.
- **Asset selector:** debounced autocomplete, curated registry view, retry and empty states.
- **Investment analysis:** calls evaluate and snapshot endpoints; projections, verdict and reasoning show only if returned. Confidence and historical evaluation are explicitly marked unavailable when absent from the documented schema.
- **Calibration:** reads calibration summary, profiles, confidence calibration and accuracy-by-sector. Calibration trigger requires explicit confirmation; a `200` response is described as trigger-request success, not assumed run completion.
- **Backtesting:** supports single-date and date-range request bodies as documented. Generic response objects are inspected defensively; long-running range requests show the backend's documented latency warning.
- **Portfolio:** allows portfolio metadata and watchlist management. Holdings, allocation, portfolio valuation and P&L remain explicitly unavailable without position-level endpoints.
- **Prompt evolution:** renders returned improvement lifecycle records and can trigger evolution after confirmation. Promote/retire buttons are omitted because no transition routes are documented.

## Backend gaps to resolve

These are capabilities missing from, or not specified by, the supplied OpenAPI excerpt. They may exist in the backend implementation but require confirmation from its actual schemas/routes.

1. **Prediction detail:** dedicated record lookup, prediction confidence, horizon/evaluation state, and stored reasoning/attributions keyed by prediction ID.
2. **Evaluation lifecycle:** pending evaluation list, evaluation submission or scheduler status, plus predicted and realized outcomes after the chosen horizon.
3. **Bias observability:** explicit names/schemas for the five bias types, timestamped bias-magnitude history, measured correction factors, and before/after calibration accuracy.
4. **Backtest response schemas:** typed request results for individual interval points, aggregate statistics, accuracy series, and equity curve. Existing result schemas are generic objects in the supplied excerpt.
5. **Portfolio positions:** holdings/positions, quantities, transactions, cost basis, current valuations, allocation weights, realized/unrealized P&L.
6. **Prompt lifecycle transitions:** dedicated promote/retire operations and allowed transition rules. Current routes expose lifecycle records and trigger-evolution only.
7. **Prompt performance:** per-prompt evaluation sample counts, hit rate/Brier score/calibration metrics, and baseline comparisons.
8. **Model leaderboard:** model identifiers and comparable hit rate, Brier score, and calibration error including baseline metrics.
9. **Response schemas:** nested `items` schemas and explicit fields for assets, dashboard metrics, recent predictions, attributions, timeline series, calibration profile records, model improvements, alerts, and portfolio list objects. The provided excerpt describes many of these as generic or omits their item shapes.
10. **Long-running operation status:** for calibration/evolution/backtest runs, a job or run identifier and a documented progress/status retrieval strategy would enable trustworthy progress indicators if operations are asynchronous.
11. **Duplicate trigger semantics:** idempotency or concurrency behavior for calibration/evolution trigger endpoints, especially after network timeouts.
12. **Security consistency:** verify root-level OpenAPI security and route-specific security requirements, especially dashboard mutation endpoints and analysis operations, before production deployment.

## Data integrity choices

- No synthetic financial metrics or sample predictions are shipped.
- Values missing from the API show an em dash or a precise unavailable explanation, not zero.
- Generic API object fields are rendered only after they exist in a real response.
- Calibration/evolution trigger actions require confirmation and prevent repeat submissions while pending.
- Network timeouts on POST trigger requests are treated as outcome-unconfirmed to reduce duplicate action risk.
