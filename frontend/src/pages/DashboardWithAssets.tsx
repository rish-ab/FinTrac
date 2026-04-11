import { useState } from 'react'
import { evaluate } from '../api/client'
import AssetSelector from '../components/AssetSelector'
import VerdictCard from '../components/VerdictCard'

// ── TYPES ──────────────────────────────────────────────────────────────────

interface AnalysisResult {
  query: {
    ticker: string
    budget: number
    horizon_years: number | null
  }
  market_data: {
    ticker: string
    company_name: string
    sector: string
    current_price: number
    currency: string
    market_cap: number | null
    pe_ratio: number | null
    dividend_yield: number | null
  }
  projection: {
    horizon_years: number
    initial_investment: number
    projected_value_low: number
    projected_value_mid: number
    projected_value_high: number
    assumed_annual_return_pct: number
  } | null
  ai_verdict: string | null
  ai_reasoning: string | null
  alternatives: Array<{ ticker: string; reason: string }> | null
}

// ── COMPONENT ──────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [selectedTicker, setSelectedTicker] = useState<string>('')
  const [budget, setBudget] = useState<number>(10000)
  const [horizon, setHorizon] = useState<number>(3)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleAssetSelect = async (ticker: string, assetClass: string) => {
    setSelectedTicker(ticker)
    setError(null)
    
    // Auto-adjust horizon based on asset class
    if (assetClass === 'forex') setHorizon(1)
    else if (assetClass === 'crypto') setHorizon(1)
    else if (assetClass === 'commodities') setHorizon(2)
    else if (assetClass === 'bonds') setHorizon(3)
    else setHorizon(5)  // equities default
  }

  const handleAnalyze = async () => {
    if (!selectedTicker) {
      setError('Please select an asset first')
      return
    }

    setLoading(true)
    setError(null)
    
    try {
      const res = await evaluate(selectedTicker, budget, undefined)
      setResult(res.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Analysis failed')
      console.error('Analysis error:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '24px' }}>
      {/* Header */}
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{
          fontSize: '28px',
          fontWeight: 700,
          color: 'var(--ft-text)',
          marginBottom: '8px',
        }}>
          Investment Analysis
        </h1>
        <p style={{
          fontSize: '14px',
          color: 'var(--ft-text-muted)',
        }}>
          Analyze stocks, FOREX, bonds, commodities, and crypto with AI-powered insights
        </p>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(400px, 1fr) 2fr',
        gap: '24px',
      }}>
        {/* Left Column: Asset Selector + Parameters */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <AssetSelector 
            onSelect={handleAssetSelect}
            selectedTicker={selectedTicker}
          />

          {/* Analysis Parameters */}
          <div className="card">
            <div className="card-header">Analysis Parameters</div>
            <div className="card-body p-3">
              <div style={{ marginBottom: '16px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '12px',
                  fontWeight: 600,
                  color: 'var(--ft-text-muted)',
                  marginBottom: '6px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                }}>
                  Investment Budget
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{
                    fontSize: '18px',
                    color: 'var(--ft-text-muted)',
                  }}>$</span>
                  <input
                    type="number"
                    value={budget}
                    onChange={(e) => setBudget(Number(e.target.value))}
                    min="100"
                    step="100"
                    style={{
                      flex: 1,
                      padding: '10px 12px',
                      background: 'var(--ft-surface)',
                      border: '1px solid var(--ft-border)',
                      borderRadius: '4px',
                      color: 'var(--ft-text)',
                      fontSize: '16px',
                      fontFamily: 'var(--ft-mono)',
                      fontWeight: 600,
                    }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '16px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '12px',
                  fontWeight: 600,
                  color: 'var(--ft-text-muted)',
                  marginBottom: '6px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                }}>
                  Time Horizon
                </label>
                <select
                  value={horizon}
                  onChange={(e) => setHorizon(Number(e.target.value))}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    background: 'var(--ft-surface)',
                    border: '1px solid var(--ft-border)',
                    borderRadius: '4px',
                    color: 'var(--ft-text)',
                    fontSize: '14px',
                  }}
                >
                  <option value={1}>1 Year</option>
                  <option value={2}>2 Years</option>
                  <option value={3}>3 Years</option>
                  <option value={5}>5 Years</option>
                  <option value={10}>10 Years</option>
                  <option value={20}>20 Years</option>
                </select>
              </div>

              <button
                onClick={handleAnalyze}
                disabled={!selectedTicker || loading}
                style={{
                  width: '100%',
                  padding: '12px',
                  background: selectedTicker && !loading ? 'var(--ft-blue)' : 'var(--ft-surface)',
                  border: 'none',
                  borderRadius: '6px',
                  color: selectedTicker && !loading ? 'white' : 'var(--ft-text-muted)',
                  fontSize: '14px',
                  fontWeight: 700,
                  cursor: selectedTicker && !loading ? 'pointer' : 'not-allowed',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                }}
              >
                {loading ? 'Analyzing...' : 'Analyze Investment'}
              </button>

              {error && (
                <div style={{
                  marginTop: '12px',
                  padding: '10px',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid var(--ft-red)',
                  borderRadius: '4px',
                  color: 'var(--ft-red)',
                  fontSize: '13px',
                }}>
                  {error}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Results */}
        <div>
          {result ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Market Data Card */}
              <div className="card">
                <div className="card-header">
                  {result.market_data.company_name || result.market_data.ticker}
                  <span style={{
                    marginLeft: '8px',
                    fontSize: '12px',
                    color: 'var(--ft-text-muted)',
                    fontWeight: 400,
                  }}>
                    {result.market_data.sector}
                  </span>
                </div>
                <div className="card-body p-3">
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(3, 1fr)',
                    gap: '16px',
                  }}>
                    <div>
                      <div className="data-key">Current Price</div>
                      <div className="data-val">
                        ${result.market_data.current_price?.toFixed(2)}
                      </div>
                    </div>
                    {result.market_data.market_cap && (
                      <div>
                        <div className="data-key">Market Cap</div>
                        <div className="data-val">
                          ${(result.market_data.market_cap / 1e9).toFixed(2)}B
                        </div>
                      </div>
                    )}
                    {result.market_data.pe_ratio && (
                      <div>
                        <div className="data-key">P/E Ratio</div>
                        <div className="data-val">
                          {result.market_data.pe_ratio.toFixed(2)}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Projection Card */}
              {result.projection && (
                <div className="card">
                  <div className="card-header">
                    {result.projection.horizon_years}-Year Projection
                  </div>
                  <div className="card-body p-3">
                    <div style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(3, 1fr)',
                      gap: '16px',
                    }}>
                      <div>
                        <div className="data-key">Bear Case</div>
                        <div className="data-val" style={{ color: 'var(--ft-red)' }}>
                          ${result.projection.projected_value_low.toLocaleString()}
                        </div>
                      </div>
                      <div>
                        <div className="data-key">Base Case</div>
                        <div className="data-val" style={{ color: 'var(--ft-amber)' }}>
                          ${result.projection.projected_value_mid.toLocaleString()}
                        </div>
                      </div>
                      <div>
                        <div className="data-key">Bull Case</div>
                        <div className="data-val" style={{ color: 'var(--ft-green)' }}>
                          ${result.projection.projected_value_high.toLocaleString()}
                        </div>
                      </div>
                    </div>
                    <div style={{
                      marginTop: '12px',
                      padding: '8px',
                      background: 'var(--ft-surface)',
                      borderRadius: '4px',
                      fontSize: '12px',
                      color: 'var(--ft-text-muted)',
                      textAlign: 'center',
                    }}>
                      Projected Annual Return: {result.projection.assumed_annual_return_pct.toFixed(1)}%
                    </div>
                  </div>
                </div>
              )}

              {/* AI Verdict Card */}
              <VerdictCard
                verdict={result.ai_verdict}
                reasoning={result.ai_reasoning}
                alternatives={result.alternatives}
              />
            </div>
          ) : (
            <div className="card">
              <div className="card-body text-center" style={{ padding: '60px 24px' }}>
                <div style={{
                  fontSize: '48px',
                  marginBottom: '16px',
                }}>📊</div>
                <p style={{
                  fontSize: '16px',
                  color: 'var(--ft-text-muted)',
                  marginBottom: '8px',
                }}>
                  Select an asset and click Analyze
                </p>
                <p style={{
                  fontSize: '13px',
                  color: 'var(--ft-text-dim)',
                }}>
                  AI-powered analysis across equities, FOREX, bonds, commodities, and crypto
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
