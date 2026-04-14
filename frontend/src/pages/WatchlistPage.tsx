import { useState, useEffect, useRef } from 'react'
import {
  getWatchlist, addToWatchlist, removeFromWatchlist, getAlerts,
} from '../api/client'
import client from '../api/client'

interface WatchlistItem {
  id: string; user_id: string; ticker: string; portfolio_id: string | null
  price_trigger_high: number | null; price_trigger_low: number | null
}

interface Alert {
  id: string; alert_type: string; trigger_value: number | null
  triggered_at: string; delivered_at: string | null
  status: string; channel: string
}

interface SearchResult {
  ticker: string; name: string; asset_class: string
}

const fmtDate = (s: string) =>
  new Date(s).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })

export default function WatchlistPage() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([])
  const [alerts, setAlerts]       = useState<Alert[]>([])
  const [tab, setTab]             = useState<'watchlist' | 'alerts'>('watchlist')
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState('')
  const [showModal, setShowModal] = useState(false)

  // Add form state
  const [ticker, setTicker]     = useState('')
  const [trigHigh, setTrigHigh] = useState('')
  const [trigLow, setTrigLow]   = useState('')
  const [adding, setAdding]     = useState(false)

  // Search
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [showSearch, setShowSearch]       = useState(false)
  const [searching, setSearching]         = useState(false)
  const searchRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()

  const load = async () => {
    try {
      const [wRes, aRes] = await Promise.all([getWatchlist(), getAlerts()])
      setWatchlist(wRes.data)
      setAlerts(aRes.data)
    } catch {
      setError('Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) setShowSearch(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // ── SEARCH ──────────────────────────────────────────────────

  const handleTickerInput = (value: string) => {
    setTicker(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)

    if (value.length < 1) {
      setSearchResults([])
      setShowSearch(false)
      return
    }

    debounceRef.current = setTimeout(async () => {
      setSearching(true)
      try {
        const res = await client.get(`/assets/search?q=${encodeURIComponent(value)}&limit=8`)
        setSearchResults(res.data)
        setShowSearch(true)
      } catch {
        // ignore
      } finally {
        setSearching(false)
      }
    }, 250)
  }

  const selectSearchResult = (r: SearchResult) => {
    setTicker(r.ticker)
    setShowSearch(false)
    setSearchResults([])
  }

  // ── CRUD ────────────────────────────────────────────────────

  const handleAdd = async () => {
    if (!ticker.trim()) return
    setAdding(true)
    setError('')
    try {
      await addToWatchlist(
        ticker.trim().toUpperCase(),
        trigHigh ? parseFloat(trigHigh) : undefined,
        trigLow  ? parseFloat(trigLow)  : undefined,
      )
      setTicker('')
      setTrigHigh('')
      setTrigLow('')
      setShowModal(false)
      load()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add to watchlist')
    } finally {
      setAdding(false)
    }
  }

  const handleRemove = async (id: string) => {
    try {
      await removeFromWatchlist(id)
      setWatchlist(prev => prev.filter(w => w.id !== id))
    } catch {
      setError('Failed to remove')
    }
  }

  return (
    <div className="page-content">
      <div className="page-title d-flex justify-content-between align-items-center">
        <span><i className="bi bi-bell" /> Watchlist & Alerts</span>
        <button className="btn btn-primary btn-sm" onClick={() => setShowModal(true)}>
          + Add Ticker
        </button>
      </div>

      {error && <div className="alert alert-danger mb-3">{error}</div>}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '4px', marginBottom: '20px', borderBottom: '1px solid var(--ft-border)', paddingBottom: '0' }}>
        {(['watchlist', 'alerts'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: 'none', border: 'none',
            borderBottom: tab === t ? '2px solid var(--ft-blue)' : '2px solid transparent',
            color: tab === t ? 'var(--ft-text)' : 'var(--ft-text-muted)',
            fontFamily: 'var(--ft-mono)', fontSize: '11px', fontWeight: 600,
            letterSpacing: '0.08em', textTransform: 'uppercase',
            padding: '8px 16px', cursor: 'pointer', marginBottom: '-1px',
          }}>
            {t === 'watchlist' ? `Watchlist (${watchlist.length})` : `Alerts (${alerts.length})`}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="ft-spinner">
          <div className="spinner-border spinner-border-sm text-primary" /> Loading...
        </div>
      ) : tab === 'watchlist' ? (
        watchlist.length === 0 ? (
          <div className="empty-state">
            <i className="bi bi-eye" />
            No tickers on watchlist. Add any ticker to start monitoring.
          </div>
        ) : (
          <div className="card">
            <table className="table table-hover mb-0">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th className="text-end">Alert High</th>
                  <th className="text-end">Alert Low</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {watchlist.map(w => (
                  <tr key={w.id}>
                    <td style={{ fontFamily: 'var(--ft-mono)', fontWeight: 600, color: 'var(--ft-blue)' }}>
                      {w.ticker}
                    </td>
                    <td className="text-end" style={{ fontFamily: 'var(--ft-mono)', color: w.price_trigger_high ? 'var(--ft-green)' : 'var(--ft-text-muted)' }}>
                      {w.price_trigger_high ? `$${w.price_trigger_high.toFixed(2)}` : '—'}
                    </td>
                    <td className="text-end" style={{ fontFamily: 'var(--ft-mono)', color: w.price_trigger_low ? 'var(--ft-red)' : 'var(--ft-text-muted)' }}>
                      {w.price_trigger_low ? `$${w.price_trigger_low.toFixed(2)}` : '—'}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn btn-outline-danger btn-sm" onClick={() => handleRemove(w.id)}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : (
        alerts.length === 0 ? (
          <div className="empty-state">
            <i className="bi bi-bell-slash" />
            No alerts fired yet. Add price triggers to your watchlist items.
          </div>
        ) : (
          <div className="card">
            <table className="table table-hover mb-0">
              <thead>
                <tr>
                  <th>Type</th>
                  <th className="text-end">Trigger</th>
                  <th>Fired At</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map(a => (
                  <tr key={a.id}>
                    <td>
                      <span style={{
                        fontFamily: 'var(--ft-mono)', fontSize: '11px', fontWeight: 600,
                        color: a.alert_type === 'PRICE_HIGH' ? 'var(--ft-green)' : 'var(--ft-red)',
                      }}>
                        {a.alert_type}
                      </span>
                    </td>
                    <td className="text-end" style={{ fontFamily: 'var(--ft-mono)' }}>
                      {a.trigger_value ? `$${a.trigger_value.toFixed(2)}` : '—'}
                    </td>
                    <td style={{ fontFamily: 'var(--ft-mono)', fontSize: '12px', color: 'var(--ft-text-dim)' }}>
                      {fmtDate(a.triggered_at)}
                    </td>
                    <td>
                      <span className={`status-${a.status.toLowerCase()}`}
                        style={{ fontFamily: 'var(--ft-mono)', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase' }}>
                        {a.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* ── ADD WATCHLIST MODAL ─────────────────────────────── */}
      {showModal && (
        <div className="modal show d-block" style={{ background: 'rgba(0,0,0,0.7)' }}>
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header">
                <span className="modal-title">Add to Watchlist</span>
                <button className="btn-close" onClick={() => { setShowModal(false); setShowSearch(false) }} />
              </div>
              <div className="modal-body">
                <div className="mb-3" ref={searchRef} style={{ position: 'relative' }}>
                  <label className="form-label">Ticker</label>
                  <input
                    className="form-control"
                    placeholder="Search: AAPL, USDINR, GOLD, BTC..."
                    value={ticker}
                    onChange={e => handleTickerInput(e.target.value.toUpperCase())}
                    onFocus={() => { if (searchResults.length > 0) setShowSearch(true) }}
                    autoFocus
                  />
                  {searching && (
                    <div style={{ position: 'absolute', right: '14px', top: '38px' }}>
                      <div className="spinner-border spinner-border-sm" style={{ width: '12px', height: '12px', borderWidth: '2px', color: 'var(--ft-blue)' }} />
                    </div>
                  )}

                  {showSearch && searchResults.length > 0 && (
                    <div style={{
                      position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200,
                      background: 'var(--ft-surface)', border: '1px solid var(--ft-border-light)',
                      borderRadius: '0 0 4px 4px', maxHeight: '200px', overflowY: 'auto',
                      boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                    }}>
                      {searchResults.map(r => (
                        <button key={`${r.asset_class}-${r.ticker}`}
                          onClick={() => selectSearchResult(r)}
                          style={{
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                            width: '100%', padding: '8px 12px', border: 'none',
                            background: 'transparent', color: 'var(--ft-text)',
                            textAlign: 'left', cursor: 'pointer', fontSize: '13px',
                            borderBottom: '1px solid var(--ft-border)',
                          }}
                          className="search-result-item"
                        >
                          <span>
                            <span style={{ fontFamily: 'var(--ft-mono)', fontWeight: 600, color: 'var(--ft-blue)', marginRight: '8px' }}>
                              {r.ticker}
                            </span>
                            <span style={{ fontSize: '11px', color: 'var(--ft-text-dim)' }}>{r.name}</span>
                          </span>
                          <span style={{
                            fontFamily: 'var(--ft-mono)', fontSize: '9px', color: 'var(--ft-text-muted)',
                            textTransform: 'uppercase',
                          }}>
                            {r.asset_class}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className="row g-3">
                  <div className="col-6">
                    <label className="form-label">Price Alert High ($)</label>
                    <input className="form-control" type="number" placeholder="e.g. 180.00"
                      value={trigHigh} onChange={e => setTrigHigh(e.target.value)} />
                  </div>
                  <div className="col-6">
                    <label className="form-label">Price Alert Low ($)</label>
                    <input className="form-control" type="number" placeholder="e.g. 120.00"
                      value={trigLow} onChange={e => setTrigLow(e.target.value)} />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button className="btn btn-outline-secondary btn-sm" onClick={() => { setShowModal(false); setShowSearch(false) }}>
                  Cancel
                </button>
                <button className="btn btn-primary btn-sm" onClick={handleAdd}
                  disabled={adding || !ticker.trim()}>
                  {adding ? 'Adding...' : 'Add to Watchlist'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <style>{`
        .search-result-item:hover { background: var(--ft-surface-2) !important; }
      `}</style>
    </div>
  )
}
