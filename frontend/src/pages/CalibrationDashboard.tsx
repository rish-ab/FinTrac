import { useState, useEffect } from 'react'
import axios from 'axios'

// ── TYPES ──────────────────────────────────────────────────────────────────

interface Metrics {
  total_predictions: number
  evaluated_predictions: number
  correct_predictions: number
  overall_accuracy_pct: number
  average_confidence: number
  total_attributions: number
}

interface SectorAccuracy {
  sector: string
  total: number
  correct: number
  accuracy_pct: number
}

interface ConfidenceBucket {
  confidence_bucket: string
  total: number
  correct: number
  accuracy_pct: number
}

interface RecentPrediction {
  ticker: string
  sector: string
  predicted_direction: string
  confidence: number
  actual_return_pct: number | null
  is_correct: boolean | null
  accuracy_score: number | null
  prediction_timestamp: string
  attribution_count: number
}

interface Attribution {
  ticker: string
  score: number
  type: string
  event_type: string
  event_title: string
  event_sentiment: number
  explanation: string
}

// ── HELPERS ────────────────────────────────────────────────────────────────

const API_BASE = '/api/v1/dashboard'

const verdictClass = (direction: string) => {
  if (direction === 'buy') return 'verdict-buy'
  if (direction === 'hold') return 'verdict-hold'
  return 'verdict-avoid'
}

const resultBadge = (correct: boolean | null) => {
  if (correct === null) return null
  return correct 
    ? <span className="badge bg-success">✓ CORRECT</span>
    : <span className="badge bg-danger">✗ WRONG</span>
}

// ── MAIN COMPONENT ─────────────────────────────────────────────────────────

export default function CalibrationDashboard() {
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [sectors, setSectors] = useState<SectorAccuracy[]>([])
  const [calibration, setCalibration] = useState<ConfidenceBucket[]>([])
  const [predictions, setPredictions] = useState<RecentPrediction[]>([])
  const [attributions, setAttributions] = useState<Attribution[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    loadDashboard()
  }, [])

  const loadDashboard = async () => {
    try {
      const [metricsRes, sectorsRes, calibRes, predsRes, attrsRes] = await Promise.all([
        axios.get(`${API_BASE}/metrics`),
        axios.get(`${API_BASE}/accuracy-by-sector`),
        axios.get(`${API_BASE}/confidence-calibration`),
        axios.get(`${API_BASE}/recent-predictions?limit=15`),
        axios.get(`${API_BASE}/top-attributions?limit=10`),
      ])

      setMetrics(metricsRes.data)
      setSectors(sectorsRes.data)
      setCalibration(calibRes.data)
      setPredictions(predsRes.data)
      setAttributions(attrsRes.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load dashboard')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="page-content">
        <div className="ft-spinner">
          <div className="spinner-border spinner-border-sm text-primary" />
          Loading V3 calibration data...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-content">
        <div className="alert alert-danger">{error}</div>
      </div>
    )
  }

  return (
    <div className="page-content">
      <div className="page-title">
        <i className="bi bi-graph-up" />
        AI Self-Calibration Dashboard
      </div>

      {/* Metric Cards */}
      <div className="row g-3 mb-4">
        {metrics && [
          { label: 'Total Predictions', value: metrics.total_predictions },
          { label: 'Evaluated', value: metrics.evaluated_predictions },
          { label: 'Correct', value: metrics.correct_predictions },
          { label: 'Accuracy', value: `${metrics.overall_accuracy_pct}%` },
          { label: 'Avg Confidence', value: metrics.average_confidence.toFixed(2) },
          { label: 'Attributions', value: metrics.total_attributions },
        ].map(m => (
          <div key={m.label} className="col-6 col-md-4 col-lg-2">
            <div className="metric-tile">
              <div className="metric-label">{m.label}</div>
              <div className="metric-value">{m.value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Sector Performance */}
      <div className="card mb-4">
        <div className="card-header">Accuracy by Sector</div>
        <div className="card-body">
          <table className="table table-hover mb-0">
            <thead>
              <tr>
                <th>Sector</th>
                <th className="text-end">Total</th>
                <th className="text-end">Correct</th>
                <th className="text-end">Accuracy</th>
              </tr>
            </thead>
            <tbody>
              {sectors.map(s => (
                <tr key={s.sector}>
                  <td>{s.sector}</td>
                  <td className="text-end" style={{ fontFamily: 'var(--ft-mono)' }}>{s.total}</td>
                  <td className="text-end" style={{ fontFamily: 'var(--ft-mono)', color: 'var(--ft-green)' }}>
                    {s.correct}
                  </td>
                  <td className="text-end">
                    <span style={{
                      fontFamily: 'var(--ft-mono)',
                      fontWeight: 600,
                      color: s.accuracy_pct >= 60 ? 'var(--ft-green)'
                           : s.accuracy_pct >= 40 ? 'var(--ft-amber)'
                           : 'var(--ft-red)'
                    }}>
                      {s.accuracy_pct}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Confidence Calibration */}
      <div className="card mb-4">
        <div className="card-header">Confidence Calibration</div>
        <div className="card-body">
          <div style={{ fontSize: '12px', color: 'var(--ft-text-muted)', marginBottom: '12px', fontFamily: 'var(--ft-mono)' }}>
            Expected: AI with 85% confidence should be correct 85% of the time. Deviation shows miscalibration.
          </div>
          <table className="table table-hover mb-0">
            <thead>
              <tr>
                <th>Confidence Range</th>
                <th className="text-end">Predictions</th>
                <th className="text-end">Actual Accuracy</th>
                <th className="text-end">Expected</th>
                <th className="text-end">Calibration Gap</th>
              </tr>
            </thead>
            <tbody>
              {calibration.map((c, idx) => {
                const expected = [55, 65, 75, 85, 95][idx]
                const gap = c.accuracy_pct - expected
                return (
                  <tr key={c.confidence_bucket}>
                    <td style={{ fontFamily: 'var(--ft-mono)' }}>{c.confidence_bucket}</td>
                    <td className="text-end" style={{ fontFamily: 'var(--ft-mono)' }}>{c.total}</td>
                    <td className="text-end">
                      <span style={{
                        fontFamily: 'var(--ft-mono)',
                        fontWeight: 600,
                        color: c.accuracy_pct >= 70 ? 'var(--ft-green)' : 'var(--ft-red)'
                      }}>
                        {c.accuracy_pct}%
                      </span>
                    </td>
                    <td className="text-end" style={{ fontFamily: 'var(--ft-mono)', color: 'var(--ft-text-dim)' }}>
                      {expected}%
                    </td>
                    <td className="text-end">
                      <span style={{
                        fontFamily: 'var(--ft-mono)',
                        fontWeight: 600,
                        color: Math.abs(gap) < 10 ? 'var(--ft-green)'
                             : Math.abs(gap) < 20 ? 'var(--ft-amber)'
                             : 'var(--ft-red)'
                      }}>
                        {gap > 0 ? '+' : ''}{gap.toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recent Predictions */}
      <div className="card mb-4">
        <div className="card-header">Recent Predictions</div>
        <div className="card-body p-0">
          <div style={{ overflowX: 'auto' }}>
            <table className="table table-hover mb-0">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Sector</th>
                  <th>Prediction</th>
                  <th className="text-end">Confidence</th>
                  <th className="text-end">Actual Return</th>
                  <th>Result</th>
                  <th className="text-end">Events</th>
                </tr>
              </thead>
              <tbody>
                {predictions.map((p, idx) => (
                  <tr key={idx}>
                    <td style={{ fontFamily: 'var(--ft-mono)', fontWeight: 600, color: 'var(--ft-blue)' }}>
                      {p.ticker}
                    </td>
                    <td style={{ fontSize: '12px', color: 'var(--ft-text-dim)' }}>
                      {p.sector}
                    </td>
                    <td>
                      <span className={verdictClass(p.predicted_direction)}
                        style={{ fontFamily: 'var(--ft-mono)', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase' }}>
                        {p.predicted_direction}
                      </span>
                    </td>
                    <td className="text-end" style={{ fontFamily: 'var(--ft-mono)' }}>
                      {(p.confidence * 100).toFixed(0)}%
                    </td>
                    <td className="text-end">
                      {p.actual_return_pct !== null ? (
                        <span style={{
                          fontFamily: 'var(--ft-mono)',
                          fontWeight: 600,
                          color: p.actual_return_pct > 0 ? 'var(--ft-green)' : 'var(--ft-red)'
                        }}>
                          {p.actual_return_pct > 0 ? '+' : ''}{p.actual_return_pct.toFixed(2)}%
                        </span>
                      ) : (
                        <span style={{ color: 'var(--ft-text-muted)' }}>—</span>
                      )}
                    </td>
                    <td>{resultBadge(p.is_correct)}</td>
                    <td className="text-end" style={{ fontFamily: 'var(--ft-mono)', fontSize: '12px', color: 'var(--ft-text-dim)' }}>
                      {p.attribution_count} events
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Top Attributions */}
      <div className="card">
        <div className="card-header">Top Event Attributions</div>
        <div className="card-body">
          {attributions.map((a, idx) => {
            const typeColor = {
              'SUPPORTING': 'var(--ft-green)',
              'CONTRADICTING': 'var(--ft-red)',
              'NEUTRAL': 'var(--ft-text-dim)'
            }[a.type] || 'var(--ft-text-dim)'

            return (
              <div key={idx} style={{
                borderLeft: '3px solid var(--ft-blue)',
                background: 'var(--ft-surface-2)',
                padding: '12px 16px',
                marginBottom: '12px',
                borderRadius: '2px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <span style={{ fontFamily: 'var(--ft-mono)', fontWeight: 600, color: 'var(--ft-blue)' }}>
                      {a.ticker}
                    </span>
                    <span className="badge" style={{ background: 'var(--ft-surface)', color: typeColor }}>
                      {a.type}
                    </span>
                    <span className="badge" style={{ background: 'var(--ft-surface)', color: 'var(--ft-amber)' }}>
                      {a.event_type}
                    </span>
                  </div>
                  <span style={{ fontFamily: 'var(--ft-mono)', fontSize: '12px', fontWeight: 600, color: 'var(--ft-blue)' }}>
                    Score: {a.score}
                  </span>
                </div>
                <div style={{ fontSize: '13px', color: 'var(--ft-text)', marginBottom: '6px' }}>
                  {a.event_title}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--ft-text-muted)', fontFamily: 'var(--ft-mono)' }}>
                  {a.explanation.substring(0, 200)}...
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
