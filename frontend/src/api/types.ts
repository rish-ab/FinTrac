/** Types derived from the supplied FinTrac OpenAPI 3.1 contract.
 * Where the spec declares a generic object or omits nested item schemas, those
 * fields remain unknown instead of being guessed.
 */
export type JsonRecord = Record<string, unknown>;

export interface ValidationIssue {
  loc: Array<string | number>;
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

export interface HTTPValidationError {
  detail?: ValidationIssue[] | string;
}

export interface UserResponse {
  id: string;
  email: string;
}

export interface TokenResponse {
  access_token: string;
  token_type?: string;
  expires_in: number;
  user: UserResponse;
}

export interface RegisterRequest {
  email: string;
  password: string;
}

export interface InvestmentQuery {
  ticker: string;
  budget: number;
  horizon_years?: number | null;
  risk_tolerance?: 'conservative' | 'moderate' | 'aggressive' | 'speculative' | null;
  question?: string | null;
}

export interface MarketSnapshot {
  ticker: string;
  company_name?: string | null;
  sector?: string | null;
  industry?: string | null;
  current_price?: number | null;
  currency?: string | null;
  market_cap?: number | null;
  pe_ratio?: number | null;
  forward_pe?: number | null;
  pb_ratio?: number | null;
  dividend_yield?: number | null;
  fifty_two_week_high?: number | null;
  fifty_two_week_low?: number | null;
  avg_volume?: number | null;
  beta?: number | null;
  analyst_target_price?: number | null;
}

export interface BudgetProjection {
  horizon_years: number;
  initial_investment: number;
  projected_value_low: number;
  projected_value_mid: number;
  projected_value_high: number;
  assumed_annual_return_pct: number;
}

export interface InvestmentAnalysisResponse {
  query: InvestmentQuery;
  market_data: MarketSnapshot;
  projection?: BudgetProjection | null;
  ai_verdict?: string | null;
  ai_reasoning?: string | null;
  alternatives?: unknown[] | null;
  effective_horizon_min?: number;
  effective_horizon_max?: number;
}

export interface PortfolioCreate {
  name: string;
  base_currency?: string;
  objective?: string | null;
}

export interface PortfolioResponse {
  id: string;
  user_id: string;
  name: string;
  base_currency: string;
  objective: string | null;
}

export interface WatchlistCreate {
  ticker: string;
  portfolio_id?: string | null;
  price_trigger_high?: number | null;
  price_trigger_low?: number | null;
  sentiment_trigger_high?: number | null;
  sentiment_trigger_low?: number | null;
}

export interface WatchlistResponse extends WatchlistCreate {
  id: string;
  user_id: string;
  portfolio_id: string | null;
  price_trigger_high: number | null;
  price_trigger_low: number | null;
  sentiment_trigger_high: number | null;
  sentiment_trigger_low: number | null;
}

export interface HoldingCreate {
  ticker: string;
  action: 'BUY' | 'SELL';
  quantity: number;
  price: number;
  notes?: string | null;
}

export interface HoldingResponse {
  position_id: string;
  ticker: string;
  quantity: number;
  avg_cost: number;
  total_cost: number;
  current_price: number | null;
  current_value: number | null;
  unrealized_pnl: number | null;
  pnl_pct: number | null;
}

export interface PortfolioSummary {
  portfolio: PortfolioResponse;
  total_invested: number;
  total_current_value: number | null;
  total_pnl: number | null;
  total_pnl_pct: number | null;
  holdings: HoldingResponse[];
}

export interface AnalysedTicker {
  ticker: string;
  sector: string | null;
  asset_class: string | null;
  analyses: number;
  last_analysed: string;
}

export interface AlertResponse {
  id: string;
  title?: string;
  alert_type: string;
  trigger_value: number | null;
  triggered_at: string;
  delivered_at: string | null;
  status: string;
  channel: string;
}

export interface BacktestRequest {
  ticker: string;
  date: string;
  budget?: number;
  horizon?: string;
}

export interface BacktestRangeRequest {
  ticker: string;
  start_date: string;
  end_date: string;
  interval_days?: number;
  budget?: number;
  horizon?: string;
}

export interface AssetSearchResult extends JsonRecord {
  ticker?: string;
  symbol?: string;
  name?: string;
  company_name?: string;
  asset_class?: string;
  class?: string;
}

export type GenericApiObject = JsonRecord;

// ── Background jobs (POST /analysis/backtest-range/jobs, GET /jobs/{id}) ──

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface BacktestPoint {
  ticker: string;
  backtest_date: string;
  horizon_label: string;
  price_at_prediction?: number | null;
  ai_verdict?: string | null;
  ai_confidence?: number | null;
  ai_reasoning?: string | null;
  price_at_evaluation?: number | null;
  actual_return_pct?: number | null;
  direction_correct?: boolean | null;
  error?: string | null;
}

export interface BacktestRangeResult {
  ticker: string;
  start_date: string;
  end_date: string;
  horizon_label: string;
  total_backtests: number;
  successful: number;
  correct: number;
  accuracy_pct: number;
  avg_confidence: number;
  avg_actual_return: number;
  results: BacktestPoint[];
}

export interface Job<TPartial = unknown, TResult = unknown> {
  id: string;
  kind: string;
  params: JsonRecord;
  status: JobStatus;
  progress: { done: number; total: number | null; message: string };
  partial: TPartial[];
  result: TResult | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export type BacktestRangeJob = Job<BacktestPoint, BacktestRangeResult>;

// ── Calibration quality (GET /dashboard/calibration-metrics) ──

export interface RateWithInterval {
  n: number;
  correct: number;
  rate: number | null;
  ci: [number, number];
}

export interface ReliabilityBucket {
  bucket: string;
  n: number;
  correct: number;
  mean_confidence: number;
  accuracy: number;
  accuracy_ci: [number, number];
}

export interface CalibrationMetrics {
  n: number;
  accuracy?: RateWithInterval;
  brier_raw?: number | null;
  brier_shown?: number | null;
  ece_raw?: number | null;
  ece_shown?: number | null;
  reliability_raw?: ReliabilityBucket[];
  by_action?: Record<string, RateWithInterval>;
  baseline_up_rate?: number;
  by_horizon?: Record<string, RateWithInterval>;
  enough_data?: boolean;
}
