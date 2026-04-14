import { useState, useEffect } from 'react'
import {
  getDashboardMetrics,
  getAccuracyBySector,
  getConfidenceCalibration,
  getRecentPredictions,
  getTopAttributions,
  getCalibrationProfiles,
  getCalibrationSummary,
  getModelImprovements,
  getImprovementSummary,
  triggerCalibration,
  triggerEvolution,
} from '../api/client'

// ── TYPES ──────────────────────────────────────────────────────────────────

interface Metrics {
  total_predictions: number
  evaluated_predictions: number
  correct_predictions: number
  overall_accuracy_pct: number
  average_confidence: number
  total_attributions: number
  active_calibrations: number
  active_improvements: number
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
  prompt_version?: string
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

interface CalibrationProfile {
  id: string
  sector: string | null
  asset_class: string | null
  bias_type: string
  bias_magnitude: number
  correction_factor: number
  sample_size: number
  detected_at: string
  scope: string
  confidence_interval: { accuracy_pct: number; avg_confidence_pct: number } | null
}

interface CalibrationSummary {
  active_profiles: number
  total_profiles_ever: number
  bias_distribution: Record<string, number>
  last_calibration_run: string | null
  avg_correction_factor: number | null
  system_status: string
}

interface ModelImprovement {
  id: string
  improvement_type: string
  status: string
  detected_issue: string
  instruction: string
  sector: string | null
  expected_improvement: string | null
  validation_metrics: any | null
  created_at: string
  activated_at: string | null
}

interface ImprovementSummary {
  status_counts: Record<string, number>
  active_by_type: Record<string, number>
  total_patches_ever: number
  current_prompt_version: string
  last_evolution_run: string | null
  system_status: string
}

// ── HELPERS ────────────────────────────────────────────────────────────────

const verdictClass = (direction: string) => {
  if (direction === 'buy') return 'verdict-buy'
  if (direction === 'hold') return 'verdict-hold'
  return 'verdict-avoid'
}

const resultBadge = (correct: boolean | null) => {
  if (correct === null) return null
  return correct 
    ? <span className="badge bg-success">CORRECT</span>
    : <span className="badge bg-danger">WRONG</span>
}

const statusColor = (s: string) => {
  if (s === 'active') return 'var(--ft-green)'
  if (s === 'testing') return 'var(--ft-amber)'
  if (s === 'proposed') return 'var(--ft-blue)'
  return 'var(--ft-text-muted)'
}

const biasColor = (type: string) => {
  if (type === 'OVERCONFIDENCE') return 'var(--ft-red)'
  if (type === 'OPTIMISM_BIAS') return 'var(--ft-amber)'
  if (type === 'PESSIMISM_BIAS') return 'var(--ft-blue)'
  if (type === 'DIRECTION_BIAS') return 'var(--ft-amber)'
  return 'var(--ft-text-dim)'
}

const formatDate = (iso: string) => {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// ── MAIN COMPONENT ─────────────────────────────────────────────────────────

export default function CalibrationDashboard() {
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [sectors, setSectors] = useState<SectorAccuracy[]>([])
  const [calibration, setCalibration] = useState<ConfidenceBucket[]>([])
  const [predictions, setPredictions] = useState<RecentPrediction[]>([])
  const [attributions, setAttributions] = useState<Attribution[]>([])
  const [calProfiles, setCalProfiles] = useState<CalibrationProfile[]>([])
  const [calSummary, setCalSummary] = useState<CalibrationSummary | null>(null)
  const [improvements, setImprovements] = useState<ModelImprovement[]>([])
  const [impSummary, setImpSummary] = useState<ImprovementSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [triggerLoading, setTriggerLoading] = useState(false)

  useEffect(() => { loadDashboard() }, [])

  const loadDashboard = async () => {
    try {
      const [
        metricsRes, sectorsRes, calibRes, predsRes, attrsRes,
        calProfilesRes, calSummaryRes, impRes, impSummaryRes,
      ] = await Promise.all([
        getDashboardMetrics(),
        getAccuracyBySector(),
        getConfidenceCalibration(),
        getRecentPredictions(15),
        getTopAttributions(10),
        getCalibrationProfiles(),
        getCalibrationSummary(),
        getModelImprovements(),
        getImprovementSummary(),
      ])

      setMetrics(metricsRes.data)
      setSectors(sectorsRes.data)
      setCalibration(calibRes.data)
      setPredictions(predsRes.data)
      setAttributions(attrsRes.data)
      setCalProfiles(calProfilesRes.data)
      setCalSummary(calSummaryRes.data)
      setImprovements(impRes.data)
      setImpSummary(impSummaryRes.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load dashboard')
    } finally {
      setLoading(false)
    }
  }

  const handleTriggerCalibration = async () => {
    setTriggerLoading(true)
    try {
      await triggerCalibration()
      await triggerEvolution()
      await loadDashboard()
    } catch (e) {
      console.error('Trigger failed:', e)
    } finally {
      setTriggerLoading(false)
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
      <div className="page-title" style={{ justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <i className="bi bi-graph-up" />
          AI Self-Calibration Dashboard
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {impSummary && (
            <span style={{
              fontFamily: 'var(--ft-mono)',
              fontSize: '10px',
              color: 'var(--ft-text-muted)',
              padding: '3px 8px',
              border: '1px solid var(--ft-border)',
              borderRadius: '2px',
            }}>
              PROMPT {impSummary.current_prompt_version}
            </span>
          )}
          <button
            className="btn btn-sm btn-outline-primary"
            onClick={handleTriggerCalibration}
            disabled={triggerLoading}
          >
            {triggerLoading ? 'Running...' : 'Run Calibration'}
          </button>
        </div>
      </div>

      {/* ── METRIC CARDS ──────────────────────────────────────── */}
      <div className="row g-3 mb-4">
        {metrics && [
          { label: 'Total Predictions', value: metrics.total_predictions },
          { label: 'Evaluated', value: metrics.evaluated_predictions },
          { label: 'Correct', value: metrics.correct_predictions },
          { label: 'Accuracy', value: `${metrics.overall_accuracy_pct}%` },
          { label: 'Avg Confidence', value: metrics.average_confidence.toFixed(2) },
          { label: 'Attributions', value: metrics.total_attributions },
          { label: 'Calibrations', value: metrics.active_calibrations, color: metrics.active_calibrations > 0 ? 'var(--ft-amber)' : undefined },
          { label: 'Improvements', value: metrics.active_improvements, color: metrics.active_improvements > 0 ? 'var(--ft-green)' : undefined },
        ].map(m => (
          <div key={m.label} className="col-6 col-md-3 col-lg-3 col-xl">
            <div className="metric-tile">
              <div className="metric-label">{m.label}</div>
              <div className="metric-value" style={{ color: (m as any).color }}>{m.value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ── CALIBRATION PROFILES (Phase 5) ────────────────────── */}
      {calProfiles.length > 0 && (
        <div className="card mb-4">
          <div className="card-header d-flex justify-content-between align-items-center">
            <span>Active Bias Corrections</span>
            <span style={{ fontFamily: 'var(--ft-mono)', fontSize: '10px', color: 'var(--ft-amber)' }}>
              {calSummary?.system_status?.toUpperCase()}
            </span>
          </div>
          <div className="card-body p-0">
            <table className="table table-hover mb-0">
              <thead>
                <tr>
                  <th>Bias Type</th>
                  <th>Scope</th>
                  <th className="text-end">Magnitude</th>
                  <th className="text-end">Correction</th>
                  <th className="text-end">Accuracy</th>
                  <th className="text-end">Confidence</th>
                  <th className="text-end">Samples</th>
                </tr>
              </thead>
              <tbody>
                {calProfiles.map(p => (
                  <tr key={p.id}>
                    <td>
                      <span style={{
                        fontFamily: 'var(--ft-mono)',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: biasColor(p.bias_type),
                      }}>
                        {p.bias_type}
                      </span>
                    </td>
                    <td style={{ fontSize: '12px', color: 'var(--ft-text-dim)' }}>
                      {p.scope}
                    </td>
                    <td className="text-end" style={{ fontFamily: 'var(--ft-mono)', color: 'var(--ft-red)' }}>
                      {(p.bias_magnitude * 100).toFixed(1)}%
                    </td>
                    <td className="text-end" style={{ fontFamily: 'var(--ft-mono)', fontWeight: 600 }}>
                      x{p.correction_factor.toFixed(3)}
                    </td>
                    <td className="text-end" style={{ fontFamily: 'var(--ft-mono)' }}>
                      {p.confidence_interval?.accuracy_pct ?? '-'}%
                    </td>
                    <td className="text-end" style={{ fontFamily: 'var(--ft-mono)' }}>
                      {p.confidence_interval?.avg_confidence_pct ?? '-'}%
                    </td>
                    <td className="text-end" style={{ fontFamily: 'var(--ft-mono)', color: 'var(--ft-text-dim)' }}>
                      {p.sample_size}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── MODEL IMPROVEMENTS (Phase 6) ──────────────────────── */}
      {improvements.length > 0 && (
        <div className="card mb-4">
          <div className="card-header d-flex justify-content-between align-items-center">
            <span>Prompt Evolution Patches</span>
            <span style={{ fontFamily: 'var(--ft-mono)', fontSize: '10px', color: 'var(--ft-green)' }}>
              {impSummary?.total_patches_ever ?? 0} TOTAL
            </span>
          </div>
          <div className="card-body p-0">
            <table className="table table-hover mb-0">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Detected Issue</th>
                  <th className="text-end">Created</th>
                </tr>
              </thead>
              <tbody>
                {improvements.map(imp => (
                  <tr key={imp.id}>
                    <td>
                      <span style={{
                        fontFamily: 'var(--ft-mono)',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: 'var(--ft-blue)',
                      }}>
                        {imp.improvement_type}
                      </span>
                      {imp.sector && (
                        <span style={{ fontSize: '11px', color: 'var(--ft-text-muted)', marginLeft: '6px' }}>
                          ({imp.sector})
                        </span>
                      )}
                    </td>
                    <td>
                      <span style={{
                        fontFamily: 'var(--ft-mono)',
                        fontSize: '10px',
                        fontWeight: 600,
                        textTransform: 'uppercase',
                        letterSpacing: '0.06em',
                        color: statusColor(imp.status),
                        padding: '2px 6px',
                        border: `1px solid ${statusColor(imp.status)}`,
                        borderRadius: '2px',
                      }}>
                        {imp.status}
                      </span>
                    </td>
                    <td style={{ fontSize: '12px', color: 'var(--ft-text-dim)', maxWidth: '400px' }}>
                      {imp.detected_issue.length > 120
                        ? imp.detected_issue.substring(0, 120) + '...'
                        : imp.detected_issue}
                    </td>
                    <td className="text-end" style={{ fontFamily: 'var(--ft-mono)', fontSize: '11px', color: 'var(--ft-text-muted)', whiteSpace: 'nowrap' }}>
                      {formatDate(imp.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── SECTOR PERFORMANCE ────────────────────────────────── */}
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

      {/* ── CONFIDENCE CALIBRATION ────────────────────────────── */}
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

      {/* ── RECENT PREDICTIONS ────────────────────────────────── */}
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
                        <span style={{ color: 'var(--ft-text-muted)', fontSize: '11px' }}>pending</span>
                      )}
                    </td>
                    <td>{resultBadge(p.is_correct)}</td>
                    <td className="text-end" style={{ fontFamily: 'var(--ft-mono)', color: 'var(--ft-text-dim)' }}>
                      {p.attribution_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ── TOP ATTRIBUTIONS ──────────────────────────────────── */}
      {attributions.length > 0 && (
        <div className="card mb-4">
          <div className="card-header">Top Event Attributions</div>
          <div className="card-body p-0">
            <div style={{ overflowX: 'auto' }}>
              <table className="table table-hover mb-0">
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th>Event</th>
                    <th>Type</th>
                    <th className="text-end">Score</th>
                    <th className="text-end">Sentiment</th>
                  </tr>
                </thead>
                <tbody>
                  {attributions.map((a, idx) => (
                    <tr key={idx}>
                      <td style={{ fontFamily: 'var(--ft-mono)', fontWeight: 600, color: 'var(--ft-blue)' }}>
                        {a.ticker}
                      </td>
                      <td style={{ fontSize: '12px', maxWidth: '300px' }}>
                        {a.event_title.length > 80 ? a.event_title.substring(0, 80) + '...' : a.event_title}
                      </td>
                      <td>
                        <span style={{
                          fontFamily: 'var(--ft-mono)',
                          fontSize: '10px',
                          fontWeight: 600,
                          color: a.type === 'SUPPORTING' ? 'var(--ft-green)'
                               : a.type === 'CONTRADICTING' ? 'var(--ft-red)'
                               : 'var(--ft-text-dim)',
                        }}>
                          {a.type}
                        </span>
                      </td>
                      <td className="text-end" style={{ fontFamily: 'var(--ft-mono)', fontWeight: 600 }}>
                        {a.score.toFixed(2)}
                      </td>
                      <td className="text-end">
                        <span style={{
                          fontFamily: 'var(--ft-mono)',
                          color: a.event_sentiment > 0 ? 'var(--ft-green)' : a.event_sentiment < 0 ? 'var(--ft-red)' : 'var(--ft-text-dim)',
                        }}>
                          {a.event_sentiment > 0 ? '+' : ''}{a.event_sentiment?.toFixed(2) ?? 'N/A'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
