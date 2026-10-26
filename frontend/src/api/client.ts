import { getAccessToken } from './token-store';
import type {
  AlertResponse,
  AssetSearchResult,
  BacktestRangeJob,
  BacktestRangeRequest,
  BacktestRequest,
  CalibrationMetrics,
  GenericApiObject,
  InvestmentAnalysisResponse,
  InvestmentQuery,
  JsonRecord,
  MarketSnapshot,
  PortfolioCreate,
  PortfolioResponse,
  RegisterRequest,
  TokenResponse,
  UserResponse,
  WatchlistCreate,
  WatchlistResponse,
} from './types';

const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
const TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 30_000);

// Endpoints that run the LLM (Mistral via Ollama) or loop over many dates
// routinely take far longer than a normal request: a single evaluation is
// ~1 minute on local hardware, and a range backtest is one LLM call per step.
// They get their own ceilings so the browser doesn't abort while the API is
// still working (the backend would finish and log 200, but the UI shows a timeout).
const SLOW_TIMEOUT_MS = {
  evaluate: 300_000,      // one LLM verdict + market data
  compare: 600_000,       // one LLM call per ticker
  backtest: 300_000,      // one historical LLM verdict
  backtestRange: 1_800_000, // one LLM verdict per interval step
  trigger: 300_000,       // calibration / prompt evolution runs
} as const;

type HttpMethod = 'GET' | 'POST' | 'DELETE';
type QueryValue = string | number | boolean | null | undefined;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  readonly requestPath: string;

  constructor(message: string, status: number, detail: unknown, requestPath: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.requestPath = requestPath;
  }
}

function withQuery(path: string, query?: Record<string, QueryValue>): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined && value !== '') params.set(key, String(value));
  }
  const suffix = params.toString();
  return suffix ? `${path}?${suffix}` : path;
}

async function request<T>(
  path: string,
  options: {
    method?: HttpMethod;
    query?: Record<string, QueryValue>;
    body?: unknown;
    form?: URLSearchParams;
    auth?: 'required' | 'none';
    timeoutMs?: number;
  } = {},
): Promise<T> {
  const method = options.method ?? 'GET';
  const requestPath = withQuery(path, options.query);
  const headers = new Headers({ Accept: 'application/json' });
  const token = options.auth === 'required' ? getAccessToken() : null;
  if (options.auth === 'required' && !token) {
    throw new ApiError('Sign in is required for this endpoint.', 401, null, requestPath);
  }
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const timeoutMs = options.timeoutMs ?? TIMEOUT_MS;
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  let body: BodyInit | undefined;
  if (options.form) {
    headers.set('Content-Type', 'application/x-www-form-urlencoded');
    body = options.form;
  } else if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json');
    body = JSON.stringify(options.body);
  }

  try {
    const response = await fetch(`${API_ORIGIN}${requestPath}`, {
      method,
      headers,
      body,
      signal: controller.signal,
    });
    if (response.status === 204) {
      if (!response.ok) throw new ApiError('Request failed', response.status, null, requestPath);
      return undefined as T;
    }

    const contentType = response.headers.get('content-type') ?? '';
    let payload: unknown = null;
    if (contentType.includes('application/json')) {
      payload = await response.json().catch(() => null);
    } else {
      payload = await response.text().catch(() => '');
    }

    if (!response.ok) {
      const detail = isRecord(payload) && 'detail' in payload ? payload.detail : payload;
      const message = validationMessage(detail) || `Request failed with status ${response.status}`;
      throw new ApiError(message, response.status, detail, requestPath);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(`Request timed out after ${Math.round(timeoutMs / 1000)} s`, 0, null, requestPath);
    }
    throw new ApiError(error instanceof Error ? error.message : 'Network request failed', 0, null, requestPath);
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function validationMessage(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (!isRecord(item)) return null;
      const loc = Array.isArray(item.loc) ? item.loc.join(' → ') : '';
      const msg = typeof item.msg === 'string' ? item.msg : '';
      return [loc, msg].filter(Boolean).join(': ');
    }).filter(Boolean);
    return parts.length ? parts.join(' · ') : null;
  }
  return null;
}

export const api = {
  // Health
  health: () => request<unknown>('/health'),

  // Auth (login deliberately uses form encoding per the OAuth2 OpenAPI schema).
  login: (username: string, password: string) => {
    const form = new URLSearchParams({ grant_type: 'password', username, password, scope: '' });
    return request<TokenResponse>('/api/v1/auth/token', { method: 'POST', form, auth: 'none' });
  },
  register: (input: RegisterRequest) => request<UserResponse>('/api/v1/auth/register', { method: 'POST', body: input, auth: 'none' }),
  me: () => request<UserResponse>('/api/v1/auth/me', { auth: 'required' }),

  // Analysis
  evaluateInvestment: (input: InvestmentQuery) => request<InvestmentAnalysisResponse>('/api/v1/analysis/evaluate', { method: 'POST', body: input, timeoutMs: SLOW_TIMEOUT_MS.evaluate }),
  marketSnapshot: (ticker: string) => request<MarketSnapshot>('/api/v1/analysis/snapshot', { query: { ticker } }),
  compareAssets: (tickers: string[], budget: number, horizonYears?: number | null) =>
    request<GenericApiObject>('/api/v1/analysis/compare', { method: 'POST', query: { budget, horizon_years: horizonYears }, body: tickers, timeoutMs: SLOW_TIMEOUT_MS.compare }),
  backtestSingle: (input: BacktestRequest) => request<GenericApiObject>('/api/v1/analysis/backtest', { method: 'POST', body: input, timeoutMs: SLOW_TIMEOUT_MS.backtest }),
  // Preferred for ranges: returns a job immediately; poll job() for progress
  startBacktestRangeJob: (input: BacktestRangeRequest) => request<BacktestRangeJob>('/api/v1/analysis/backtest-range/jobs', { method: 'POST', body: input }),
  backtestRange: (input: BacktestRangeRequest) => request<GenericApiObject>('/api/v1/analysis/backtest-range', { method: 'POST', body: input, timeoutMs: SLOW_TIMEOUT_MS.backtestRange }),

  // Assets
  searchAssets: (q: string, limit = 15) => request<AssetSearchResult[]>('/api/v1/assets/search', { query: { q, limit } }),
  assetRegistry: () => request<GenericApiObject>('/api/v1/assets/registry'),
  assetList: () => request<GenericApiObject>('/api/v1/assets/list'),
  exampleAssets: () => request<GenericApiObject>('/api/v1/assets/examples'),

  // Background jobs
  job: <T = BacktestRangeJob>(jobId: string) => request<T>(`/api/v1/jobs/${encodeURIComponent(jobId)}`),
  cancelJob: (jobId: string) => request<GenericApiObject>(`/api/v1/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' }),

  // Dashboard
  dashboardMetrics: () => request<GenericApiObject>('/api/v1/dashboard/metrics'),
  accuracyBySector: () => request<GenericApiObject[]>('/api/v1/dashboard/accuracy-by-sector'),
  confidenceCalibration: () => request<GenericApiObject[]>('/api/v1/dashboard/confidence-calibration'),
  recentPredictions: (limit = 20) => request<GenericApiObject[]>('/api/v1/dashboard/recent-predictions', { query: { limit } }),
  topAttributions: (limit = 15) => request<GenericApiObject[]>('/api/v1/dashboard/top-attributions', { query: { limit } }),
  predictionTimeline: (days = 30) => request<GenericApiObject>('/api/v1/dashboard/timeline', { query: { days } }),
  calibrationProfiles: () => request<GenericApiObject[]>('/api/v1/dashboard/calibration-profiles'),
  calibrationMetrics: () => request<CalibrationMetrics>('/api/v1/dashboard/calibration-metrics'),
  calibrationSummary: () => request<GenericApiObject>('/api/v1/dashboard/calibration-summary'),
  triggerCalibration: () => request<GenericApiObject>('/api/v1/dashboard/trigger-calibration', { method: 'POST', timeoutMs: SLOW_TIMEOUT_MS.trigger }),
  modelImprovements: () => request<GenericApiObject[]>('/api/v1/dashboard/model-improvements'),
  improvementSummary: () => request<GenericApiObject>('/api/v1/dashboard/improvement-summary'),
  triggerEvolution: () => request<GenericApiObject>('/api/v1/dashboard/trigger-evolution', { method: 'POST', timeoutMs: SLOW_TIMEOUT_MS.trigger }),

  // Portfolios & watchlist
  portfolios: () => request<PortfolioResponse[]>('/api/v1/portfolios/', { auth: 'required' }),
  createPortfolio: (input: PortfolioCreate) => request<PortfolioResponse>('/api/v1/portfolios/', { method: 'POST', body: input, auth: 'required' }),
  portfolio: (portfolioId: string) => request<PortfolioResponse>(`/api/v1/portfolios/${encodeURIComponent(portfolioId)}`, { auth: 'required' }),
  deletePortfolio: (portfolioId: string) => request<void>(`/api/v1/portfolios/${encodeURIComponent(portfolioId)}`, { method: 'DELETE', auth: 'required' }),
  watchlist: () => request<WatchlistResponse[]>('/api/v1/portfolios/watchlist', { auth: 'required' }),
  addWatchlistItem: (input: WatchlistCreate) => request<WatchlistResponse>('/api/v1/portfolios/watchlist', { method: 'POST', body: input, auth: 'required' }),
  removeWatchlistItem: (watchlistId: string) => request<void>(`/api/v1/portfolios/watchlist/${encodeURIComponent(watchlistId)}`, { method: 'DELETE', auth: 'required' }),

  // Alerts
  alerts: (status?: string, limit = 50) => request<AlertResponse[]>('/api/v1/alerts/', { query: { status, limit }, auth: 'required' }),
} as const;

export type ApiClient = typeof api;
