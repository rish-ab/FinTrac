import { useState, useEffect } from 'react'
import { getPortfolios, createPortfolio, deletePortfolio } from '../api/client'

interface Portfolio {
  id: string; user_id: string; name: string
  base_currency: string; objective: string | null
}

export default function PortfolioPage() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [name, setName]             = useState('')
  const [objective, setObjective]   = useState('')
  const [loading, setLoading]       = useState(true)
  const [creating, setCreating]     = useState(false)
  const [error, setError]           = useState('')
  const [showModal, setShowModal]   = useState(false)

  const load = async () => {
    try {
      const res = await getPortfolios()
      setPortfolios(res.data)
    } catch {
      setError('Failed to load portfolios')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    if (!name.trim()) return
    setCreating(true)
    try {
      await createPortfolio(name.trim(), objective || undefined)
      setName('')
      setObjective('')
      setShowModal(false)
      load()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create portfolio')
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this portfolio?')) return
    try {
      await deletePortfolio(id)
      setPortfolios(prev => prev.filter(p => p.id !== id))
    } catch {
      setError('Failed to delete portfolio')
    }
  }

  const objectiveColor = (obj: string | null) => {
    if (obj === 'GROWTH') return 'var(--ft-green)'
    if (obj === 'INCOME') return 'var(--ft-blue)'
    if (obj === 'PRESERVATION') return 'var(--ft-amber)'
    return 'var(--ft-text-muted)'
  }

  return (
    <div className="page-content">
      <div className="page-title d-flex justify-content-between align-items-center">
        <span><i className="bi bi-briefcase" /> Portfolios</span>
        <button className="btn btn-primary btn-sm" onClick={() => setShowModal(true)}>
          + New Portfolio
        </button>
      </div>

      {error && <div className="alert alert-danger mb-3">{error}</div>}

      {loading ? (
        <div className="ft-spinner">
          <div className="spinner-border spinner-border-sm text-primary" />
          Loading...
        </div>
      ) : portfolios.length === 0 ? (
        <div className="empty-state">
          <i className="bi bi-briefcase" />
          No portfolios yet — create one to get started.
        </div>
      ) : (
        <div className="card">
          <table className="table table-hover mb-0">
            <thead>
              <tr>
                <th>Name</th>
                <th>Currency</th>
                <th>Objective</th>
                <th>ID</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {portfolios.map(p => (
                <tr key={p.id}>
                  <td style={{ fontWeight: 500 }}>{p.name}</td>
                  <td style={{ fontFamily: 'var(--ft-mono)' }}>{p.base_currency}</td>
                  <td>
                    <span style={{ fontFamily: 'var(--ft-mono)', fontSize: '11px', color: objectiveColor(p.objective) }}>
                      {p.objective || '—'}
                    </span>
                  </td>
                  <td style={{ fontFamily: 'var(--ft-mono)', fontSize: '11px', color: 'var(--ft-text-muted)' }}>
                    {p.id.slice(0, 8)}...
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      className="btn btn-outline-danger btn-sm"
                      onClick={() => handleDelete(p.id)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create modal */}
      {showModal && (
        <div className="modal show d-block" style={{ background: 'rgba(0,0,0,0.7)' }}>
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header">
                <span className="modal-title">New Portfolio</span>
                <button className="btn-close" onClick={() => setShowModal(false)} />
              </div>
              <div className="modal-body">
                <div className="mb-3">
                  <label className="form-label">Portfolio Name</label>
                  <input
                    className="form-control"
                    placeholder="Retirement Fund"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    autoFocus
                  />
                </div>
                <div className="mb-3">
                  <label className="form-label">Objective</label>
                  <select
                    className="form-select"
                    value={objective}
                    onChange={e => setObjective(e.target.value)}
                  >
                    <option value="">Select objective</option>
                    <option value="GROWTH">Growth</option>
                    <option value="INCOME">Income</option>
                    <option value="PRESERVATION">Preservation</option>
                  </select>
                </div>
              </div>
              <div className="modal-footer">
                <button className="btn btn-outline-secondary btn-sm" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={handleCreate}
                  disabled={creating || !name.trim()}
                >
                  {creating ? 'Creating...' : 'Create'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
