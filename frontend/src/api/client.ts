// =============================================================
// src/api/client.ts
//
// Central axios instance. All API calls go through here.
//
// The request interceptor automatically attaches the JWT to
// every request. The response interceptor catches 401s and
// redirects to login — handles token expiry transparently.
// =============================================================

import axios from 'axios'

const client = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// Attach token to every request
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('ft_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Redirect to login on 401
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

// ── API FUNCTIONS ──────────────────────────────────────────────

// Auth
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

// Analysis
export const evaluate = (ticker: string, budget: number, question?: string) =>
  client.post('/analysis/evaluate', { ticker, budget, question })

// Portfolios
export const getPortfolios = () => client.get('/portfolios/')
export const createPortfolio = (name: string, objective?: string) =>
  client.post('/portfolios/', { name, objective })
export const deletePortfolio = (id: string) => client.delete(`/portfolios/${id}`)

// Watchlist
export const getWatchlist = () => client.get('/portfolios/watchlist')
export const addToWatchlist = (
  ticker: string,
  priceTriggerHigh?: number,
  priceTriggerLow?: number
) =>
  client.post('/portfolios/watchlist', {
    ticker,
    price_trigger_high: priceTriggerHigh || null,
    price_trigger_low:  priceTriggerLow  || null,
  })
export const removeFromWatchlist = (id: string) =>
  client.delete(`/portfolios/watchlist/${id}`)

// Alerts
export const getAlerts = () => client.get('/alerts/')
