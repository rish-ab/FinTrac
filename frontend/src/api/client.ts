// =============================================================
// src/api/client.ts — Central axios instance
// V3 Phase 8: Added holdings, portfolio summary, search, backtest
// =============================================================

import axios from 'axios'

const client = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('ft_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('ft_token')
      localStorage.removeItem('ft_user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default client

// ── AUTH ───────────────────────────────────────────────────────
export const register = (email: string, password: string) =>
  client.post('/auth/register', { email, password })

export const login = (email: string, password: string) => {
  const form = new URLSearchParams()
  form.append('username', email)
  form.append('password', password)
  return client.post('/auth/token', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
}

// ── ANALYSIS ──────────────────────────────────────────────────
export const evaluate = (
  ticker: string, budget: number, question?: string, horizon_years?: number,
) =>
  client.post('/analysis/evaluate', {
    ticker, budget,
    question: question || undefined,
    horizon_years: horizon_years || undefined,
  })

export const getSnapshot = (ticker: string) =>
  client.get(`/analysis/snapshot?ticker=${encodeURIComponent(ticker)}`)

// ── ASSETS / SEARCH ───────────────────────────────────────────
export const searchAssets = (query: string, limit = 12) =>
  client.get(`/assets/search?q=${encodeURIComponent(query)}&limit=${limit}`)

// ── PORTFOLIOS ────────────────────────────────────────────────
export const getPortfolios = () => client.get('/portfolios/')
export const createPortfolio = (name: string, objective?: string) =>
  client.post('/portfolios/', { name, objective })
export const deletePortfolio = (id: string) => client.delete(`/portfolios/${id}`)

// Holdings
export const getPortfolioSummary = (portfolioId: string) =>
  client.get(`/portfolios/${portfolioId}/summary`)

export const getHoldings = (portfolioId: string) =>
  client.get(`/portfolios/${portfolioId}/holdings`)

export const addHolding = (
  portfolioId: string, ticker: string, quantity: number, price: number, action = 'BUY',
) =>
  client.post(`/portfolios/${portfolioId}/holdings`, {
    ticker, quantity, price, action,
  })

export const closePosition = (portfolioId: string, positionId: string) =>
  client.delete(`/portfolios/${portfolioId}/holdings/${positionId}`)

// ── WATCHLIST ─────────────────────────────────────────────────
export const getWatchlist = () => client.get('/portfolios/watchlist')
export const addToWatchlist = (
  ticker: string, priceTriggerHigh?: number, priceTriggerLow?: number,
) =>
  client.post('/portfolios/watchlist', {
    ticker,
    price_trigger_high: priceTriggerHigh || null,
    price_trigger_low: priceTriggerLow || null,
  })
export const removeFromWatchlist = (id: string) =>
  client.delete(`/portfolios/watchlist/${id}`)

// ── ALERTS ────────────────────────────────────────────────────
export const getAlerts = () => client.get('/alerts/')

// ── V3 DASHBOARD ──────────────────────────────────────────────
const DASH = '/dashboard'
export const getDashboardMetrics = () => client.get(`${DASH}/metrics`)
export const getAccuracyBySector = () => client.get(`${DASH}/accuracy-by-sector`)
export const getConfidenceCalibration = () => client.get(`${DASH}/confidence-calibration`)
export const getRecentPredictions = (limit = 15) => client.get(`${DASH}/recent-predictions?limit=${limit}`)
export const getTopAttributions = (limit = 10) => client.get(`${DASH}/top-attributions?limit=${limit}`)
export const getPredictionTimeline = (days = 30) => client.get(`${DASH}/timeline?days=${days}`)
export const getCalibrationProfiles = () => client.get(`${DASH}/calibration-profiles`)
export const getCalibrationSummary = () => client.get(`${DASH}/calibration-summary`)
export const triggerCalibration = () => client.post(`${DASH}/trigger-calibration`)
export const getModelImprovements = () => client.get(`${DASH}/model-improvements`)
export const getImprovementSummary = () => client.get(`${DASH}/improvement-summary`)
export const triggerEvolution = () => client.post(`${DASH}/trigger-evolution`)

// ── BACKTEST ──────────────────────────────────────────────────
export const backtestSingle = (
  ticker: string, date: string, budget = 10000, horizon = '1m',
) =>
  client.post('/analysis/backtest', { ticker, date, budget, horizon })

export const backtestRange = (
  ticker: string, startDate: string, endDate: string,
  intervalDays = 30, budget = 10000, horizon = '1m',
) =>
  client.post('/analysis/backtest-range', {
    ticker, start_date: startDate, end_date: endDate,
    interval_days: intervalDays, budget, horizon,
  })
