import { useState, useEffect, useRef } from 'react'
import client from '../api/client'

// ── TYPES ──────────────────────────────────────────────────────────────────

interface AssetExample {
  ticker: string
  name: string
  asset_class?: string
}

interface AssetCategories {
  equities: AssetExample[]
  forex: AssetExample[]
  bonds: AssetExample[]
  commodities: AssetExample[]
  crypto: AssetExample[]
  indices: AssetExample[]
}

interface SearchResult {
  ticker: string
  name: string
  asset_class: string
  yf_symbol?: string
}

interface AssetSelectorProps {
  onSelect: (ticker: string, assetClass: string) => void
  selectedTicker?: string
}

// ── COMPONENT ──────────────────────────────────────────────────────────────

export default function AssetSelector({ onSelect, selectedTicker }: AssetSelectorProps) {
  const [activeTab, setActiveTab] = useState<keyof AssetCategories>('equities')
  const [assets, setAssets] = useState<AssetCategories | null>(null)
  const [loading, setLoading] = useState(true)
  
  // Search state
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [showResults, setShowResults] = useState(false)
  const searchRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => { loadAssets() }, [])

  // Close search dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowResults(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const loadAssets = async () => {
    try {
      const res = await client.get('/assets/examples')
      setAssets(res.data)
    } catch (err) {
      console.error('Failed to load assets:', err)
    } finally {
      setLoading(false)
    }
  }

  // ── SEARCH LOGIC ────────────────────────────────────────────

  const handleSearchInput = (value: string) => {
    setSearchQuery(value)
    
    // Clear previous debounce
    if (debounceRef.current) clearTimeout(debounceRef.current)
    
    if (value.length < 1) {
      setSearchResults([])
      setShowResults(false)
      return
    }
    
    // Debounce: wait 300ms after last keystroke
    debounceRef.current = setTimeout(async () => {
      setSearching(true)
      try {
        const res = await client.get(`/assets/search?q=${encodeURIComponent(value)}&limit=12`)
        setSearchResults(res.data)
        setShowResults(true)
      } catch (err) {
        console.error('Search failed:', err)
      } finally {
        setSearching(false)
      }
    }, 300)
  }

  const handleSearchSelect = (result: SearchResult) => {
    setSearchQuery('')
    setShowResults(false)
    setSearchResults([])
    onSelect(result.ticker, result.asset_class.toLowerCase())
  }

  const handleDirectSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (searchQuery.trim()) {
      onSelect(searchQuery.trim().toUpperCase(), 'custom')
      setSearchQuery('')
      setShowResults(false)
    }
  }

  const handleSelect = (ticker: string) => {
    onSelect(ticker, activeTab)
  }

  // ── ASSET CLASS BADGE ───────────────────────────────────────

  const classColor = (cls: string) => {
    const colors: Record<string, string> = {
      EQUITY: 'var(--ft-blue)',
      FOREX: 'var(--ft-green)',
      BOND: 'var(--ft-text-dim)',
      COMMODITY: 'var(--ft-amber)',
      CRYPTO: '#a78bfa',
      INDEX: 'var(--ft-text-muted)',
    }
    return colors[cls] || 'var(--ft-text-dim)'
  }

  if (loading) {
    return (
      <div className="card">
        <div className="card-body text-center">
          <span style={{ color: 'var(--ft-text-muted)', fontSize: '13px' }}>Loading assets...</span>
        </div>
      </div>
    )
  }

  const tabs: Array<{ key: keyof AssetCategories; label: string }> = [
    { key: 'equities',    label: 'Stocks' },
    { key: 'forex',       label: 'Forex' },
    { key: 'crypto',      label: 'Crypto' },
    { key: 'commodities', label: 'Commodities' },
    { key: 'bonds',       label: 'Bonds' },
    { key: 'indices',     label: 'Indices' },
  ]

  const currentAssets = assets?.[activeTab] || []

  return (
    <div className="card">
      <div className="card-header">Select Asset to Analyze</div>
      <div className="card-body p-3">
        
        {/* ── SEARCH BAR ───────────────────────────────────────── */}
        <div ref={searchRef} style={{ position: 'relative', marginBottom: '16px' }}>
          <form onSubmit={handleDirectSubmit}>
            <div style={{ position: 'relative' }}>
              <i className="bi bi-search" style={{
                position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)',
                color: 'var(--ft-text-muted)', fontSize: '13px',
              }} />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => handleSearchInput(e.target.value)}
                onFocus={() => { if (searchResults.length > 0) setShowResults(true) }}
                placeholder="Search any ticker... AAPL, USDINR, BTC, GOLD"
                style={{
                  width: '100%',
                  padding: '10px 12px 10px 36px',
                  background: 'var(--ft-surface-2)',
                  border: '1px solid var(--ft-border-light)',
                  borderRadius: '4px',
                  color: 'var(--ft-text)',
                  fontSize: '13px',
                  fontFamily: 'var(--ft-mono)',
                }}
              />
              {searching && (
                <div style={{
                  position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)',
                }}>
                  <div className="spinner-border spinner-border-sm" style={{ width: '14px', height: '14px', borderWidth: '2px', color: 'var(--ft-blue)' }} />
                </div>
              )}
            </div>
          </form>
          
          {/* Search Results Dropdown */}
          {showResults && searchResults.length > 0 && (
            <div style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              right: 0,
              zIndex: 100,
              background: 'var(--ft-surface)',
              border: '1px solid var(--ft-border-light)',
              borderTop: 'none',
              borderRadius: '0 0 4px 4px',
              maxHeight: '280px',
              overflowY: 'auto',
              boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
            }}>
              {searchResults.map((r) => (
                <button
                  key={`${r.asset_class}-${r.ticker}`}
                  onClick={() => handleSearchSelect(r)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    width: '100%',
                    padding: '10px 14px',
                    border: 'none',
                    background: selectedTicker === r.ticker ? 'var(--ft-surface-2)' : 'transparent',
                    color: 'var(--ft-text)',
                    textAlign: 'left',
                    cursor: 'pointer',
                    borderBottom: '1px solid var(--ft-border)',
                    transition: 'background 0.1s',
                  }}
                  className="search-result-item"
                >
                  <div>
                    <span style={{
                      fontFamily: 'var(--ft-mono)',
                      fontSize: '13px',
                      fontWeight: 600,
                      color: 'var(--ft-blue)',
                      marginRight: '10px',
                    }}>
                      {r.ticker}
                    </span>
                    <span style={{ fontSize: '12px', color: 'var(--ft-text-dim)' }}>
                      {r.name}
                    </span>
                  </div>
                  <span style={{
                    fontFamily: 'var(--ft-mono)',
                    fontSize: '9px',
                    fontWeight: 600,
                    letterSpacing: '0.08em',
                    color: classColor(r.asset_class),
                    padding: '2px 6px',
                    border: `1px solid ${classColor(r.asset_class)}`,
                    borderRadius: '2px',
                    textTransform: 'uppercase',
                  }}>
                    {r.asset_class}
                  </span>
                </button>
              ))}
              
              {/* Direct submit option */}
              {searchQuery.length >= 2 && (
                <button
                  onClick={handleDirectSubmit}
                  style={{
                    display: 'block',
                    width: '100%',
                    padding: '10px 14px',
                    border: 'none',
                    background: 'transparent',
                    color: 'var(--ft-text-muted)',
                    textAlign: 'left',
                    cursor: 'pointer',
                    fontSize: '12px',
                    fontFamily: 'var(--ft-mono)',
                  }}
                >
                  Try "{searchQuery.toUpperCase()}" as custom ticker →
                </button>
              )}
            </div>
          )}
          
          {/* No results state */}
          {showResults && searchQuery.length >= 2 && searchResults.length === 0 && !searching && (
            <div style={{
              position: 'absolute',
              top: '100%', left: 0, right: 0, zIndex: 100,
              background: 'var(--ft-surface)',
              border: '1px solid var(--ft-border-light)',
              borderTop: 'none',
              borderRadius: '0 0 4px 4px',
              padding: '14px',
              boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
            }}>
              <div style={{ fontSize: '12px', color: 'var(--ft-text-muted)', marginBottom: '8px' }}>
                No matches in registry.
              </div>
              <button
                onClick={handleDirectSubmit}
                style={{
                  padding: '8px 14px',
                  background: 'var(--ft-blue)',
                  border: 'none',
                  borderRadius: '4px',
                  color: 'white',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontFamily: 'var(--ft-mono)',
                }}
              >
                Analyze "{searchQuery.toUpperCase()}" directly
              </button>
            </div>
          )}
        </div>

        {/* ── TAB NAVIGATION ───────────────────────────────────── */}
        <div style={{
          display: 'flex',
          gap: '4px',
          marginBottom: '12px',
          borderBottom: '1px solid var(--ft-border)',
          paddingBottom: '8px',
          overflowX: 'auto',
        }}>
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                padding: '5px 10px',
                border: 'none',
                background: activeTab === tab.key ? 'var(--ft-surface-2)' : 'transparent',
                color: activeTab === tab.key ? 'var(--ft-text)' : 'var(--ft-text-muted)',
                borderRadius: '3px',
                cursor: 'pointer',
                fontSize: '11px',
                fontFamily: 'var(--ft-mono)',
                fontWeight: activeTab === tab.key ? 600 : 400,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                whiteSpace: 'nowrap',
                transition: 'all 0.15s',
              }}
              className="asset-tab-btn"
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* ── ASSET GRID ───────────────────────────────────────── */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
          gap: '6px',
          maxHeight: '220px',
          overflowY: 'auto',
        }}>
          {currentAssets.map((asset) => (
            <button
              key={asset.ticker}
              onClick={() => handleSelect(asset.ticker)}
              style={{
                padding: '8px 10px',
                border: selectedTicker === asset.ticker 
                  ? '1.5px solid var(--ft-blue)' 
                  : '1px solid var(--ft-border)',
                background: selectedTicker === asset.ticker
                  ? 'rgba(45, 126, 247, 0.08)'
                  : 'var(--ft-surface)',
                borderRadius: '4px',
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'all 0.15s',
              }}
              className="asset-item-btn"
            >
              <div style={{
                fontFamily: 'var(--ft-mono)',
                fontSize: '12px',
                fontWeight: 600,
                color: 'var(--ft-blue)',
                marginBottom: '1px',
              }}>
                {asset.ticker}
              </div>
              <div style={{
                fontSize: '10px',
                color: 'var(--ft-text-dim)',
                lineHeight: '1.2',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {asset.name}
              </div>
            </button>
          ))}
        </div>
      </div>

      <style>{`
        .asset-tab-btn:hover {
          background: var(--ft-surface-2) !important;
          color: var(--ft-text) !important;
        }
        .asset-item-btn:hover {
          border-color: var(--ft-blue) !important;
          background: rgba(45, 126, 247, 0.05) !important;
        }
        .search-result-item:hover {
          background: var(--ft-surface-2) !important;
        }
      `}</style>
    </div>
  )
}
