interface VerdictCardProps {
  verdict: string | null
  reasoning: string | null
  alternatives: { ticker: string; reason: string }[] | null
}

export default function VerdictCard({ verdict, reasoning, alternatives }: VerdictCardProps) {
  if (!verdict) {
    return (
      <div className="card">
        <div className="card-header">AI Verdict</div>
        <div className="card-body">
          <p style={{ color: 'var(--ft-text-muted)', fontFamily: 'var(--ft-mono)', fontSize: '12px' }}>
            AI analysis unavailable — Ollama may be offline.
          </p>
        </div>
      </div>
    )
  }

  const verdictClass = verdict === 'BUY' ? 'buy' : verdict === 'HOLD' ? 'hold' : 'avoid'
  const verdictColor = verdict === 'BUY'
    ? 'var(--ft-green)' : verdict === 'HOLD'
    ? 'var(--ft-amber)' : 'var(--ft-red)'

  return (
    <div className="card">
      <div className="card-header d-flex justify-content-between align-items-center">
        <span>AI Verdict</span>
        <span style={{
          fontFamily: 'var(--ft-mono)',
          fontSize: '13px',
          fontWeight: 700,
          color: verdictColor,
          letterSpacing: '0.1em',
        }}>
          {verdict}
        </span>
      </div>
      <div className="card-body p-3">
        {reasoning && (
          <div className={`verdict-block ${verdictClass} mb-3`}>
            {reasoning}
          </div>
        )}
        {alternatives && alternatives.length > 0 && (
          <>
            <div className="data-key mb-2">Alternatives</div>
            {alternatives.map((a) => (
              <div key={a.ticker} className="data-row">
                <span className="data-val" style={{ color: 'var(--ft-blue)' }}>{a.ticker}</span>
                <span style={{ fontSize: '12px', color: 'var(--ft-text-dim)', maxWidth: '60%', textAlign: 'right' }}>
                  {a.reason}
                </span>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
