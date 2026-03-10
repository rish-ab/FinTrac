import { useState, FormEvent } from 'react'
import { evaluate } from '../api/client'
import VerdictCard from '../components/VerdictCard'

interface MarketData {
  ticker: string; company_name: string; sector: string; industry: string
  current_price: number; currency: string; market_cap: number
  pe_ratio: number; forward_pe: number; pb_ratio: number
  dividend_yield: number; fifty_two_week_high: number; fifty_two_week_low: number
  avg_volume: number; beta: number; analyst_target_price: number
}

interface Projection {
  horizon_years: number; initial_investment: number
  projected_value_low: number; projected_value_mid: number
  projected_value_high: number; assumed_annual_return_pct: number
}

interface EvalResult {
  market_data: MarketData
  projection: Projection
  ai_verdict: string | null
  ai_reasoning: string | null
  alternatives: { ticker: string; reason: string }[] | null
}

const fmt = (n: number | null, prefix = '', decimals = 2) =>
  n == null ? 'N/A' : `${prefix}${n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`

const fmtB = (n: number | null) =>
  n == null ? 'N/A' : `$${(n / 1e9).toFixed(1)}B`

export default function DashboardPage() {
  const [ticker, setTicker]   = useState('')
  const [budget, setBudget]   = useState('10000')
  const [question, setQuestion] = useState('')
  const [result, setResult]   = useState<EvalResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!ticker.trim()) return
    setError('')
    setLoading(true)
    setResult(null)
    try {
      const res = await evaluate(
        ticker.trim().toUpperCase(),
        parseFloat(budget),
        question || undefined
      )
      setResult(res.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  const md = result?.market_data
  const proj = result?.projection

  return (
    <div className="page-content">
      <div className="page-title">
        <i className="bi bi-graph-up-arrow" />
        Investment Analysis
      </div>

      {/* Search bar */}
      <div className="ticker-search">
        <div style={{ flex: '0 0 120px' }}>
          <label className="form-label">Ticker</label>
          <input
            className="form-control"
            placeholder="XOM"
            value={ticker}
            onChange={e => setTicker(e.target.value.toUpperCase())}
            style={{ textTransform: 'uppercase' }}
          />
        </div>
        <div style={{ flex: '0 0 150px' }}>
          <label className="form-label">Budget (USD)</label>
          <input
            className="form-control"
            type="number"
            placeholder="10000"
            value={budget}
            onChange={e => setBudget(e.target.value)}
          />
        </div>
        <div style={{ flex: 1 }}>
          <label className="form-label">Question (optional)</label>
          <input
            className="form-control"
            placeholder="What are the key risks in recent filings?"
            value={question}
            onChange={e => setQuestion(e.target.value)}
          />
        </div>
        <div>
          <button
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={loading || !ticker.trim()}
            style={{ height: '42px' }}
          >
            {loading ? 'Analysing...' : 'Analyse'}
          </button>
        </div>
      </div>

      {error && <div className="alert alert-danger mb-3">{error}</div>}

      {loading && (
        <div className="ft-spinner">
          <div className="spinner-border spinner-border-sm text-primary" />
          Running analysis — Mistral is processing...
        </div>
      )}

      {result && md && (
        <>
          {/* Company header */}
          <div className="mb-3" style={{ display: 'flex', alignItems: 'baseline', gap: '14px' }}>
            <span style={{ fontFamily: 'var(--ft-mono)', fontSize: '24px', fontWeight: 600 }}>
              {md.ticker}
            </span>
            <span style={{ color: 'var(--ft-text-dim)', fontSize: '14px' }}>
              {md.company_name}
            </span>
            <span className="badge" style={{ background: 'var(--ft-surface-2)', color: 'var(--ft-text-dim)', marginLeft: 'auto' }}>
              {md.sector}
            </span>
          </div>

          {/* Metric tiles */}
          <div className="row g-3 mb-4">
            {[
              { label: 'Current Price', value: fmt(md.current_price, '$') },
              { label: 'Market Cap',    value: fmtB(md.market_cap) },
              { label: 'P/E Ratio',     value: fmt(md.pe_ratio, '', 2) },
              { label: 'Forward P/E',   value: fmt(md.forward_pe, '', 2) },
              { label: 'Beta',          value: fmt(md.beta, '', 3) },
              { label: 'Dividend Yield',value: md.dividend_yield ? `${md.dividend_yield.toFixed(2)}%` : 'N/A' },
            ].map(m => (
              <div key={m.label} className="col-6 col-md-4 col-lg-2">
                <div className="metric-tile">
                  <div className="metric-label">{m.label}</div>
                  <div className="metric-value">{m.value}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="row g-3 mb-4">
            {/* Market data detail */}
            <div className="col-md-4">
              <div className="card h-100">
                <div className="card-header">Market Data</div>
                <div className="card-body p-3">
                  {[
                    ['52W High',       fmt(md.fifty_two_week_high, '$')],
                    ['52W Low',        fmt(md.fifty_two_week_low, '$')],
                    ['P/B Ratio',      fmt(md.pb_ratio)],
                    ['Avg Volume',     md.avg_volume ? `${(md.avg_volume/1e6).toFixed(1)}M` : 'N/A'],
                    ['Analyst Target', fmt(md.analyst_target_price, '$')],
                    ['Industry',       md.industry || 'N/A'],
                  ].map(([k, v]) => (
                    <div key={k} className="data-row">
                      <span className="data-key">{k}</span>
                      <span className="data-val">{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Projection */}
            {proj && (
              <div className="col-md-4">
                <div className="card h-100">
                  <div className="card-header">
                    {proj.horizon_years}Y Projection — ${proj.initial_investment.toLocaleString()}
                  </div>
                  <div className="card-body p-3">
                    {[
                      ['CAGR (hist.)',   `${proj.assumed_annual_return_pct.toFixed(1)}%`],
                      ['Low scenario',   fmt(proj.projected_value_low, '$', 0)],
                      ['Mid scenario',   fmt(proj.projected_value_mid, '$', 0)],
                      ['High scenario',  fmt(proj.projected_value_high, '$', 0)],
                    ].map(([k, v]) => (
                      <div key={k} className="data-row">
                        <span className="data-key">{k}</span>
                        <span className="data-val" style={{
                          color: k === 'High scenario' ? 'var(--ft-green)'
                               : k === 'Low scenario'  ? 'var(--ft-red)'
                               : 'var(--ft-text)',
                        }}>{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* AI Verdict */}
            <div className="col-md-4">
              <VerdictCard
                verdict={result.ai_verdict}
                reasoning={result.ai_reasoning}
                alternatives={result.alternatives}
              />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
