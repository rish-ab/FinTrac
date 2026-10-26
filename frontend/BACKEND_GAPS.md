# FinTrac V3 — Backend gaps

This list is based on the OpenAPI excerpt supplied for frontend implementation. It distinguishes absent/unspecified API contract details from assertions about the backend implementation; some capabilities may exist but were not included in the supplied specification.

| Requested capability | Current documented support | Additional contract needed |
|---|---|---|
| Dashboard summary and recent activity | Metrics, recent predictions, timeline, confidence calibration, sector accuracy, attributions, calibration summary exist | Explicit item schemas and metric fields, including pending/evaluated counts and named overall accuracy fields |
| Prediction detail | Recent-predictions list and investment analysis exist | Read one prediction by ID; document confidence, predicted direction/price, horizon, reasoning, timestamps, and evaluation status |
| Delayed evaluation | No dedicated route shown | Pending evaluation list, evaluation results, submit/force-evaluate action if applicable, and realized values after the horizon |
| Five bias types | Calibration summary/profiles and confidence calibration exist | Canonical bias identifiers/names, severity scale, magnitude and timestamps, affected predictions, and applicable correction factor schema |
| Calibration impact | **Partly resolved:** `GET /dashboard/calibration-metrics` returns Brier/ECE for raw vs shown confidence, reliability buckets with Wilson intervals, per-action and per-horizon hit rates, and sample size (rendered in the Calibration quality panel) | Correction-factor history over time and a run ID/status for calibration runs |
| Backtest detail/results | Single-date and range endpoints exist; responses are generic objects | Typed response models for individual predictions/outcomes, aggregate statistics, accuracy series, and equity/performance curve |
| Portfolio holdings and P&L | Portfolio metadata CRUD and watchlist CRUD exist | Positions/holdings, units, entry/cost basis, trades, mark prices, valuation timestamp, allocation basis, realized/unrealized P&L calculations |
| Prompt lifecycle | Improvement list/summary and trigger-evolution exist; summary describes proposed/testing/active/retired | Per-prompt schema, metrics by prompt, allowed transition rules, promote/retire operations, and transition audit trail |
| Multi-model leaderboard | No documented route | Model/baseline identifiers, comparable hit rate, Brier score, calibration error, metric definitions, and sample counts |
| Asset registry/search | Search/list/registry/examples routes exist | Full nested item schemas for ticker, display name, asset class, exchange/currency, and any result source metadata |
| Alerts | List endpoint exists | Full alert item schema was provided; if creating/updating/dismissing alerts is needed, those routes are not documented |
| Long-running jobs | **Resolved for range backtests:** `POST /analysis/backtest-range/jobs` returns a job; `GET /jobs/{id}` gives status, progress, per-date partial results and the final result; `POST /jobs/{id}/cancel` stops it. One AI-heavy job runs at a time (others queue). Jobs are in API memory and are lost on restart | Same treatment for calibration/evolution triggers if they become slow; persistence if jobs must survive API restarts |
| API security | OAuth2 password flow is documented; some routes explicitly declare security | Confirm root-level security and security requirements for each route in the complete OpenAPI document, especially trigger endpoints |

## Frontend behavior until gaps are resolved

- No guessed route is called.
- Generic object payloads are shown defensively using actual keys, while richer time series/tables appear only when real response fields can be recognized.
- Missing confidence, evaluation status, bias history, P&L, or lifecycle actions are labeled unavailable rather than replaced with synthetic values.
- Trigger actions use a confirmation dialog and do not claim completion when the response only confirms that the request succeeded.
