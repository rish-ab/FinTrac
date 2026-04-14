import { useState, useEffect } from 'react'
import {
  getPortfolios, createPortfolio, deletePortfolio,
  getPortfolioSummary, addHolding, closePosition,
} from '../api/client'

// ── TYPES ──────────────────────────────────────────────────────────────────

interface Portfolio {
  id: string; user_id: string; name: string
  base_currency: string; objective: string | null
}

interface Holding {
  position_id: string; ticker: string; quantity: number
  avg_cost: number; total_cost: number
  current_price: number | null; current_value: number | null
  unrealized_pnl: number | null; pnl_pct: number | null
}

interface Summary {
  portfolio: Portfolio
  total_invested: number
  total_current_value: number | null
  total_pnl: number | null
  total_pnl_pct: number | null
  holdings: Holding[]
}

// ── HELPERS ────────────────────────────────────────────────────────────────

const pnlColor = (v: number | null) =>
  v === null ? 'var(--ft-text-muted)' : v >= 0 ? 'var(--ft-green)' : 'var(--ft-red)'

const fmtMoney = (v: number | null) =>
  v === null ? '—' : `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

const fmtPct = (v: number | null) =>
  v === null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`

const objectiveColor = (obj: string | null) => {
  if (obj === 'GROWTH') return 'var(--ft-green)'
  if (obj === 'INCOME') return 'var(--ft-blue)'
  if (obj === 'PRESERVATION') return 'var(--ft-amber)'
  return 'var(--ft-text-muted)'
}

// ── COMPONENT ──────────────────────────────────────────────────────────────

export default function PortfolioPage() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [activeSummary, setActiveSummary] = useState<Summary | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [error, setError] = useState('')

  // Create portfolio modal
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newObjective, setNewObjective] = useState('')
  const [creating, setCreating] = useState(false)

  // Add holding modal
  const [showAddHolding, setShowAddHolding] = useState(false)
  const [holdTicker, setHoldTicker] = useState('')
  const [holdQty, setHoldQty] = useState('')
  const [holdPrice, setHoldPrice] = useState('')
  const [holdAction, setHoldAction] = useState('BUY')
  const [addingHolding, setAddingHolding] = useState(false)

  useEffect(() => { loadPortfolios() }, [])

  const loadPortfolios = async () => {
    try {
      const res = await getPortfolios()
      setPortfolios(res.data)
      // Auto-select first portfolio
      if (res.data.length > 0 && !activeId) {
        loadSummary(res.data[0].id)
      }
    } catch {
      setError('Failed to load portfolios')
    } finally {
      setLoading(false)
    }
  }

  const loadSummary = async (id: string) => {
    setActiveId(id)
    setSummaryLoading(true)
    setError('')
    try {
      const res = await getPortfolioSummary(id)
      setActiveSummary(res.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load portfolio')
    } finally {
      setSummaryLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    try {
      const res = await createPortfolio(newName.trim(), newObjective || undefined)
      setNewName('')
      setNewObjective('')
      setShowCreate(false)
      await loadPortfolios()
      loadSummary(res.data.id)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create')
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this portfolio and all its holdings?')) return
    try {
      await deletePortfolio(id)
      setPortfolios(prev => prev.filter(p => p.id !== id))
      if (activeId === id) {
        setActiveId(null)
        setActiveSummary(null)
      }
    } catch {
      setError('Failed to delete')
    }
  }

  const handleAddHolding = async () => {
    if (!activeId || !holdTicker.trim() || !holdQty || !holdPrice) return
    setAddingHolding(true)
    setError('')
    try {
      await addHolding(
        activeId,
        holdTicker.trim().toUpperCase(),
        parseFloat(holdQty),
        parseFloat(holdPrice),
        holdAction,
      )
      setHoldTicker('')
      setHoldQty('')
      setHoldPrice('')
      setHoldAction('BUY')
      setShowAddHolding(false)
      loadSummary(activeId)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add holding')
    } finally {
      setAddingHolding(false)
    }
  }

  const handleClosePosition = async (posId: string) => {
    if (!activeId || !confirm('Close this position?')) return
    try {
      await closePosition(activeId, posId)
      loadSummary(activeId)
    } catch {
      setError('Failed to close position')
    }
  }

  // ── RENDER ──────────────────────────────────────────────────

  return (
    <div className="page-content">
      <div className="page-title d-flex justify-content-between align-items-center">
        <span><i className="bi bi-briefcase" /> Portfolios</span>
        <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)}>
          + New Portfolio
        </button>
      </div>

      {error && <div className="alert alert-danger mb-3">{error}</div>}

      {loading ? (
        <div className="ft-spinner">
          <div className="spinner-border spinner-border-sm text-primary" /> Loading...
        </div>
      ) : portfolios.length === 0 ? (
        <div className="empty-state">
          <i className="bi bi-briefcase" />
          No portfolios yet. Create one to start tracking your investments.
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: '20px' }}>
          {/* ── PORTFOLIO LIST (left sidebar) ─────────────────── */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {portfolios.map(p => (
              <button
                key={p.id}
                onClick={() => loadSummary(p.id)}
                style={{
                  padding: '14px 16px',
                  border: activeId === p.id ? '1.5px solid var(--ft-blue)' : '1px solid var(--ft-border)',
                  background: activeId === p.id ? 'rgba(45,126,247,0.08)' : 'var(--ft-surface)',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.15s',
                }}
              >
                <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--ft-text)', marginBottom: '4px' }}>
                  {p.name}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{
                    fontFamily: 'var(--ft-mono)', fontSize: '10px', fontWeight: 600,
                    color: objectiveColor(p.objective), textTransform: 'uppercase',
                  }}>
                    {p.objective || 'No objective'}
                  </span>
                  <span style={{
                    fontFamily: 'var(--ft-mono)', fontSize: '10px', color: 'var(--ft-text-muted)',
                  }}>
                    {p.base_currency}
                  </span>
                </div>
              </button>
            ))}
          </div>

          {/* ── PORTFOLIO DETAIL (right panel) ────────────────── */}
          <div>
            {summaryLoading ? (
              <div className="ft-spinner">
                <div className="spinner-border spinner-border-sm text-primary" /> Loading holdings...
              </div>
            ) : activeSummary ? (
              <>
                {/* Summary cards */}
                <div className="row g-3 mb-4">
                  <div className="col-6 col-md-3">
                    <div className="metric-tile">
                      <div className="metric-label">Invested</div>
                      <div className="metric-value">{fmtMoney(activeSummary.total_invested)}</div>
                    </div>
                  </div>
                  <div className="col-6 col-md-3">
                    <div className="metric-tile">
                      <div className="metric-label">Current Value</div>
                      <div className="metric-value">{fmtMoney(activeSummary.total_current_value)}</div>
                    </div>
                  </div>
                  <div className="col-6 col-md-3">
                    <div className="metric-tile">
                      <div className="metric-label">Total P&L</div>
                      <div className="metric-value" style={{ color: pnlColor(activeSummary.total_pnl) }}>
                        {fmtMoney(activeSummary.total_pnl)}
                      </div>
                    </div>
                  </div>
                  <div className="col-6 col-md-3">
                    <div className="metric-tile">
                      <div className="metric-label">Return</div>
                      <div className="metric-value" style={{ color: pnlColor(activeSummary.total_pnl_pct) }}>
                        {fmtPct(activeSummary.total_pnl_pct)}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Holdings table */}
                <div className="card">
                  <div className="card-header d-flex justify-content-between align-items-center">
                    <span>Holdings ({activeSummary.holdings.length})</span>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button className="btn btn-primary btn-sm" onClick={() => setShowAddHolding(true)}>
                        + Add Holding
                      </button>
                      <button className="btn btn-outline-danger btn-sm" onClick={() => handleDelete(activeId!)}>
                        Delete Portfolio
                      </button>
                    </div>
                  </div>
                  {activeSummary.holdings.length === 0 ? (
                    <div className="card-body">
                      <div className="empty-state" style={{ padding: '30px' }}>
                        <i className="bi bi-plus-circle" />
                        No holdings. Click "Add Holding" to record a purchase.
                      </div>
                    </div>
                  ) : (
                    <div className="card-body p-0">
                      <table className="table table-hover mb-0">
                        <thead>
                          <tr>
                            <th>Ticker</th>
                            <th className="text-end">Shares</th>
                            <th className="text-end">Avg Cost</th>
                            <th className="text-end">Current</th>
                            <th className="text-end">Value</th>
                            <th className="text-end">P&L</th>
                            <th className="text-end">Return</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {activeSummary.holdings.map(h => (
                            <tr key={h.position_id}>
                              <td style={{ fontFamily: 'var(--ft-mono)', fontWeight: 600, color: 'var(--ft-blue)' }}>
                                {h.ticker}
                              </td>
                              <td className="text-end" style={{ fontFamily: 'var(--ft-mono)' }}>
                                {h.quantity.toFixed(h.quantity % 1 === 0 ? 0 : 4)}
                              </td>
                              <td className="text-end" style={{ fontFamily: 'var(--ft-mono)' }}>
                                ${h.avg_cost.toFixed(2)}
                              </td>
                              <td className="text-end" style={{ fontFamily: 'var(--ft-mono)' }}>
                                {h.current_price ? `$${h.current_price.toFixed(2)}` : '—'}
                              </td>
                              <td className="text-end" style={{ fontFamily: 'var(--ft-mono)' }}>
                                {fmtMoney(h.current_value)}
                              </td>
                              <td className="text-end" style={{ fontFamily: 'var(--ft-mono)', fontWeight: 600, color: pnlColor(h.unrealized_pnl) }}>
                                {fmtMoney(h.unrealized_pnl)}
                              </td>
                              <td className="text-end" style={{ fontFamily: 'var(--ft-mono)', fontWeight: 600, color: pnlColor(h.pnl_pct) }}>
                                {fmtPct(h.pnl_pct)}
                              </td>
                              <td className="text-end">
                                <button className="btn btn-outline-danger btn-sm" onClick={() => handleClosePosition(h.position_id)}>
                                  Close
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="card">
                <div className="card-body text-center" style={{ padding: '60px 24px' }}>
                  <i className="bi bi-arrow-left" style={{ fontSize: '32px', color: 'var(--ft-border-light)', display: 'block', marginBottom: '12px' }} />
                  <p style={{ color: 'var(--ft-text-muted)' }}>Select a portfolio to view holdings</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── CREATE PORTFOLIO MODAL ─────────────────────────── */}
      {showCreate && (
        <div className="modal show d-block" style={{ background: 'rgba(0,0,0,0.7)' }}>
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header">
                <span className="modal-title">New Portfolio</span>
                <button className="btn-close" onClick={() => setShowCreate(false)} />
              </div>
              <div className="modal-body">
                <div className="mb-3">
                  <label className="form-label">Portfolio Name</label>
                  <input className="form-control" placeholder="Retirement Fund" value={newName}
                    onChange={e => setNewName(e.target.value)} autoFocus />
                </div>
                <div className="mb-3">
                  <label className="form-label">Objective</label>
                  <select className="form-select" value={newObjective} onChange={e => setNewObjective(e.target.value)}>
                    <option value="">Select objective</option>
                    <option value="GROWTH">Growth</option>
                    <option value="INCOME">Income</option>
                    <option value="PRESERVATION">Preservation</option>
                  </select>
                </div>
              </div>
              <div className="modal-footer">
                <button className="btn btn-outline-secondary btn-sm" onClick={() => setShowCreate(false)}>Cancel</button>
                <button className="btn btn-primary btn-sm" onClick={handleCreate} disabled={creating || !newName.trim()}>
                  {creating ? 'Creating...' : 'Create'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── ADD HOLDING MODAL ──────────────────────────────── */}
      {showAddHolding && (
        <div className="modal show d-block" style={{ background: 'rgba(0,0,0,0.7)' }}>
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header">
                <span className="modal-title">Add Holding</span>
                <button className="btn-close" onClick={() => setShowAddHolding(false)} />
              </div>
              <div className="modal-body">
                <div className="mb-3">
                  <label className="form-label">Action</label>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    {['BUY', 'SELL'].map(a => (
                      <button key={a} onClick={() => setHoldAction(a)}
                        className={`btn btn-sm ${holdAction === a ? (a === 'BUY' ? 'btn-primary' : 'btn-outline-danger') : 'btn-outline-secondary'}`}
                        style={{ flex: 1 }}>
                        {a}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="mb-3">
                  <label className="form-label">Ticker</label>
                  <input className="form-control" placeholder="AAPL" value={holdTicker}
                    onChange={e => setHoldTicker(e.target.value.toUpperCase())} autoFocus />
                </div>
                <div className="row g-3">
                  <div className="col-6">
                    <label className="form-label">Shares / Quantity</label>
                    <input className="form-control" type="number" step="0.01" placeholder="10"
                      value={holdQty} onChange={e => setHoldQty(e.target.value)} />
                  </div>
                  <div className="col-6">
                    <label className="form-label">Price per Share ($)</label>
                    <input className="form-control" type="number" step="0.01" placeholder="150.00"
                      value={holdPrice} onChange={e => setHoldPrice(e.target.value)} />
                  </div>
                </div>
                {holdQty && holdPrice && (
                  <div style={{
                    marginTop: '16px', padding: '10px', background: 'var(--ft-surface-2)',
                    borderRadius: '4px', fontFamily: 'var(--ft-mono)', fontSize: '13px',
                    textAlign: 'center', color: 'var(--ft-text-dim)',
                  }}>
                    Total: ${(parseFloat(holdQty || '0') * parseFloat(holdPrice || '0')).toFixed(2)}
                  </div>
                )}
              </div>
              <div className="modal-footer">
                <button className="btn btn-outline-secondary btn-sm" onClick={() => setShowAddHolding(false)}>Cancel</button>
                <button className="btn btn-primary btn-sm" onClick={handleAddHolding}
                  disabled={addingHolding || !holdTicker.trim() || !holdQty || !holdPrice}>
                  {addingHolding ? 'Recording...' : `Record ${holdAction}`}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
