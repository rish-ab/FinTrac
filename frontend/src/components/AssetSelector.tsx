import { useState, useEffect } from 'react'
import client from '../api/client'

// ── TYPES ──────────────────────────────────────────────────────────────────

interface AssetExample {
  ticker: string
  name: string
}

interface AssetCategories {
  equities: AssetExample[]
  forex: AssetExample[]
  bonds: AssetExample[]
  commodities: AssetExample[]
  crypto: AssetExample[]
}

interface AssetSelectorProps {
  onSelect: (ticker: string, assetClass: string) => void
  selectedTicker?: string
}

// ── COMPONENT ──────────────────────────────────────────────────────────────

export default function AssetSelector({ onSelect, selectedTicker }: AssetSelectorProps) {
  const [activeTab, setActiveTab] = useState<keyof AssetCategories>('equities')
  const [assets, setAssets] = useState<AssetCategories | null>(null)
  const [customTicker, setCustomTicker] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadAssets()
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

  const handleSelect = (ticker: string) => {
    onSelect(ticker, activeTab)
  }

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (customTicker.trim()) {
      onSelect(customTicker.trim().toUpperCase(), 'custom')
      setCustomTicker('')
    }
  }

  if (loading) {
    return (
      <div className="card">
        <div className="card-body text-center">
          <span style={{ color: 'var(--ft-text-muted)', fontSize: '13px' }}>
            Loading assets...
          </span>
        </div>
      </div>
    )
  }

  if (!assets) {
    return (
      <div className="card">
        <div className="card-body text-center">
          <span style={{ color: 'var(--ft-red)', fontSize: '13px' }}>
            Failed to load asset categories
          </span>
        </div>
      </div>
    )
  }

  const tabs: Array<{ key: keyof AssetCategories; label: string; icon: string }> = [
    { key: 'equities', label: 'Stocks', icon: '📈' },
    { key: 'forex', label: 'FOREX', icon: '💱' },
    { key: 'bonds', label: 'Bonds', icon: '🏦' },
    { key: 'commodities', label: 'Commodities', icon: '📊' },
    { key: 'crypto', label: 'Crypto', icon: '₿' },
  ]

  const currentAssets = assets[activeTab] || []

  return (
    <div className="card">
      <div className="card-header">Select Asset to Analyze</div>
      <div className="card-body p-3">
        {/* Tab Navigation */}
        <div style={{
          display: 'flex',
          gap: '8px',
          marginBottom: '16px',
          borderBottom: '1px solid var(--ft-border)',
          paddingBottom: '8px',
          overflowX: 'auto',
        }}>
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                padding: '6px 12px',
                border: 'none',
                background: activeTab === tab.key ? 'var(--ft-surface-elevated)' : 'transparent',
                color: activeTab === tab.key ? 'var(--ft-text)' : 'var(--ft-text-muted)',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '13px',
                fontWeight: activeTab === tab.key ? 600 : 400,
                transition: 'all 0.2s',
                whiteSpace: 'nowrap',
                fontFamily: 'var(--ft-sans)',
              }}
              className="asset-tab-btn"
            >
              <span style={{ marginRight: '4px' }}>{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>

        {/* Asset List */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
          gap: '8px',
          marginBottom: '16px',
          maxHeight: '240px',
          overflowY: 'auto',
        }}>
          {currentAssets.map((asset) => (
            <button
              key={asset.ticker}
              onClick={() => handleSelect(asset.ticker)}
              style={{
                padding: '10px 12px',
                border: selectedTicker === asset.ticker 
                  ? '1.5px solid var(--ft-blue)' 
                  : '1px solid var(--ft-border)',
                background: selectedTicker === asset.ticker
                  ? 'rgba(59, 130, 246, 0.1)'
                  : 'var(--ft-surface)',
                borderRadius: '6px',
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'all 0.2s',
              }}
              className="asset-item-btn"
            >
              <div style={{
                fontFamily: 'var(--ft-mono)',
                fontSize: '13px',
                fontWeight: 600,
                color: 'var(--ft-blue)',
                marginBottom: '2px',
              }}>
                {asset.ticker}
              </div>
              <div style={{
                fontSize: '11px',
                color: 'var(--ft-text-dim)',
                lineHeight: '1.3',
              }}>
                {asset.name}
              </div>
            </button>
          ))}
        </div>

        {/* Custom Ticker Input */}
        <div style={{
          borderTop: '1px solid var(--ft-border)',
          paddingTop: '12px',
        }}>
          <div style={{
            fontSize: '11px',
            color: 'var(--ft-text-muted)',
            marginBottom: '6px',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
          }}>
            Or enter custom ticker
          </div>
          <form onSubmit={handleCustomSubmit} style={{ display: 'flex', gap: '8px' }}>
            <input
              type="text"
              value={customTicker}
              onChange={(e) => setCustomTicker(e.target.value)}
              placeholder="e.g., AAPL, MSFT, XOM"
              style={{
                flex: 1,
                padding: '8px 12px',
                background: 'var(--ft-surface)',
                border: '1px solid var(--ft-border)',
                borderRadius: '4px',
                color: 'var(--ft-text)',
                fontSize: '13px',
                fontFamily: 'var(--ft-mono)',
              }}
            />
            <button
              type="submit"
              style={{
                padding: '8px 16px',
                background: 'var(--ft-blue)',
                border: 'none',
                borderRadius: '4px',
                color: 'white',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Analyze
            </button>
          </form>
        </div>
      </div>

      {/* Add hover styles */}
      <style>{`
        .asset-tab-btn:hover {
          background: var(--ft-surface-elevated) !important;
        }
        .asset-item-btn:hover {
          border-color: var(--ft-blue) !important;
          background: rgba(59, 130, 246, 0.05) !important;
        }
      `}</style>
    </div>
  )
}
