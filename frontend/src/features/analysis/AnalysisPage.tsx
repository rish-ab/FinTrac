import { useEffect, useState, type FormEvent } from 'react';
import { ArrowRight, BrainCircuit, ExternalLink, LoaderCircle, Search, ShieldAlert } from 'lucide-react';
import { ApiError, api } from '../../api/client';
import type { InvestmentAnalysisResponse, MarketSnapshot } from '../../api/types';
import { formatCurrency, safeText } from '../../lib/format';
import Panel from '../../components/ui/Panel';
import MetricCard from '../../components/ui/MetricCard';
import StatePanel from '../../components/ui/StatePanel';
import StatusBadge from '../../components/ui/StatusBadge';

interface AnalysisPageProps { selectedTicker?: string; onTickerConsumed: () => void; }

const snapshotFields: Array<{ key: keyof MarketSnapshot; label: string; currency?: boolean; percent?: boolean }> = [
  { key: 'current_price', label: 'Current price', currency: true },
  { key: 'market_cap', label: 'Market cap', currency: true },
  { key: 'pe_ratio', label: 'P/E ratio' },
  { key: 'forward_pe', label: 'Forward P/E' },
  { key: 'pb_ratio', label: 'P/B ratio' },
  { key: 'dividend_yield', label: 'Dividend yield', percent: true },
  { key: 'fifty_two_week_high', label: '52-week high', currency: true },
  { key: 'fifty_two_week_low', label: '52-week low', currency: true },
  { key: 'avg_volume', label: 'Average volume' },
  { key: 'beta', label: 'Beta' },
  { key: 'analyst_target_price', label: 'Analyst target', currency: true },
];

export default function AnalysisPage({ selectedTicker, onTickerConsumed }: AnalysisPageProps) {
  const [ticker, setTicker] = useState(selectedTicker ?? '');
  const [budget, setBudget] = useState('10000');
  const [horizonYears, setHorizonYears] = useState('1');
  const [riskTolerance, setRiskTolerance] = useState('moderate');
  const [question, setQuestion] = useState('');
  const [analysis, setAnalysis] = useState<InvestmentAnalysisResponse | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<Error | null>(null);
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [snapshotError, setSnapshotError] = useState<Error | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    if (selectedTicker) { setTicker(selectedTicker); setAnalysis(null); setSnapshot(null); onTickerConsumed(); }
  }, [selectedTicker, onTickerConsumed]);

  async function runAnalysis(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAnalysisLoading(true); setAnalysisError(null); setAnalysis(null);
    try {
      const response = await api.evaluateInvestment({
        ticker: ticker.trim().toUpperCase(), budget: Number(budget),
        horizon_years: horizonYears ? Number(horizonYears) : null,
        risk_tolerance: riskTolerance as InvestmentAnalysisResponse['query']['risk_tolerance'],
        question: question.trim() || null,
      });
      setAnalysis(response);
    } catch (reason) { setAnalysisError(reason instanceof Error ? reason : new Error('Analysis request failed')); }
    finally { setAnalysisLoading(false); }
  }

  async function loadSnapshot() {
    if (!ticker.trim()) return;
    setSnapshotLoading(true); setSnapshotError(null); setSnapshot(null);
    try { setSnapshot(await api.marketSnapshot(ticker.trim().toUpperCase())); }
    catch (reason) { setSnapshotError(reason instanceof Error ? reason : new Error('Market snapshot failed')); }
    finally { setSnapshotLoading(false); }
  }

  const projection = analysis?.projection;
  const numericBudget = Number(budget);
  const apiHorizon = Number(horizonYears);
  const formInvalid = !ticker.trim() || !Number.isFinite(numericBudget) || numericBudget <= 0 || (horizonYears !== '' && (!Number.isFinite(apiHorizon) || apiHorizon < 0.08 || apiHorizon > 50));

  return <div className="page-stack">
    <div className="page-intro"><div><p className="eyebrow">MODEL ANALYSIS</p><h2 className="page-title">Investment analysis</h2><p className="page-description">Run an API-backed analysis and inspect the verdict, reasoning, projection, and market snapshot.</p></div></div>
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[.82fr_1.4fr]">
      <Panel title="Analysis request" subtitle="POST /api/v1/analysis/evaluate">
        <form id="analysis-form" className="space-y-4" onSubmit={runAnalysis}>
          <label className="form-label">Ticker<input className="input-control mt-2 font-mono uppercase" value={ticker} onChange={(event) => setTicker(event.target.value.toUpperCase())} placeholder="e.g. XOM" required minLength={1} maxLength={10} /></label>
          <label className="form-label">Investment amount (USD)<input className="input-control mt-2 font-mono" type="number" min="0.01" step="any" value={budget} onChange={(event) => setBudget(event.target.value)} required /></label>
          <label className="form-label">Horizon (years)<input className="input-control mt-2 font-mono" type="number" min="0.08" max="50" step="any" value={horizonYears} onChange={(event) => setHorizonYears(event.target.value)} /><span className="mt-1 block text-[11px] text-mutedText">API range: 0.08–50 years. Leave blank to use API defaults.</span></label>
          <label className="form-label">Risk tolerance<select className="input-control mt-2" value={riskTolerance} onChange={(event) => setRiskTolerance(event.target.value)}><option value="conservative">Conservative</option><option value="moderate">Moderate</option><option value="aggressive">Aggressive</option><option value="speculative">Speculative</option></select></label>
          <label className="form-label">Optional question<textarea className="input-control mt-2 min-h-20 resize-y" value={question} maxLength={500} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask a specific question about this investment…" /></label>
          <button className="button-primary w-full justify-center" type="submit" disabled={analysisLoading || formInvalid}>{analysisLoading ? <LoaderCircle size={15} className="animate-spin" /> : <BrainCircuit size={15} />}{analysisLoading ? 'Running analysis…' : 'Evaluate investment'}<ArrowRight size={14} /></button>
          {analysisError && <StatePanel mode="error" error={analysisError} onRetry={() => { const form = document.getElementById('analysis-form'); if (form instanceof HTMLFormElement) form.requestSubmit(); }} title={analysisError instanceof ApiError && analysisError.status === 422 ? 'Validation error' : undefined} description={analysisError.message} />}
        </form>
      </Panel>

      <div className="space-y-4">
        {!analysis && !analysisLoading && !analysisError && <Panel title="Analysis output" subtitle="Awaiting a successful API response"><StatePanel mode="empty" title="No analysis run yet" description="Submit an investment query to populate the verdict, reasoning, and projection from the backend." /></Panel>}
        {analysisLoading && <Panel title="Analysis output"><StatePanel mode="loading" title="Waiting for analysis response" /></Panel>}
        {analysis && <>
          <Panel title="AI verdict" subtitle="Verdict and reasoning as returned by the backend" action={<StatusBadge value="API response" />}>
            {analysis.ai_verdict ? <div className="flex items-start gap-3"><div className="rounded-lg border border-line bg-raised p-3"><BrainCircuit size={21} className="text-accent" /></div><div className="min-w-0"><h3 className="text-base font-semibold text-primaryText">{analysis.ai_verdict}</h3><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-secondaryText">{analysis.ai_reasoning || 'The API did not return reasoning for this response.'}</p></div></div> : <StatePanel mode="unavailable" title="No AI verdict returned" description="The analysis response did not include an ai_verdict value." />}
            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3 text-xs text-secondaryText"><span>Confidence score:</span><StatusBadge value="Not exposed by this response schema" /><span className="ml-1">Evaluation status:</span><StatusBadge value="Analysis response — not a recorded horizon evaluation" /></div>
          </Panel>
          {projection && <Panel title="Projection range" subtitle="Scenario values returned by the API (not guaranteed outcomes)">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3"><MetricCard label="Low projection" value={formatCurrency(projection.projected_value_low)} detail={`${projection.horizon_years} year horizon`} /><MetricCard label="Mid projection" value={formatCurrency(projection.projected_value_mid)} detail={`Assumed return ${projection.assumed_annual_return_pct}%`} /><MetricCard label="High projection" value={formatCurrency(projection.projected_value_high)} detail={`Initial investment ${formatCurrency(projection.initial_investment)}`} /></div>
            <p className="mt-3 text-xs leading-5 text-secondaryText">These are backend-generated projection scenarios, not evaluated prediction outcomes. The response does not provide a confidence score or actual-vs-predicted evaluation record.</p>
          </Panel>}
          {!projection && <Panel title="Projection range"><StatePanel mode="unavailable" title="Projection not returned" description="The projection field is null or absent in the analysis response." /></Panel>}
          <Panel title="Market data" subtitle="Snapshot embedded in the analysis response">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3"><MetricCard label="Current price" value={formatCurrency(analysis.market_data.current_price, analysis.market_data.currency ?? 'USD')} detail={analysis.market_data.currency ?? 'Currency not supplied'} /><MetricCard label="Market cap" value={formatCurrency(analysis.market_data.market_cap, analysis.market_data.currency ?? 'USD')} /><MetricCard label="Sector" value={analysis.market_data.sector ?? '—'} /></div>
            <button type="button" className="mt-3 text-xs font-medium text-accent hover:text-lime-300" onClick={() => setShowRaw((value) => !value)}>{showRaw ? 'Hide' : 'Show'} response details <ExternalLink size={12} className="ml-1 inline" /></button>
            {showRaw && <pre className="mt-3 max-h-72 overflow-auto rounded-lg border border-line bg-canvas p-3 text-xs leading-5 text-secondaryText">{JSON.stringify(analysis, null, 2)}</pre>}
          </Panel>
        </>}
      </div>
    </div>

    <Panel title="Raw market snapshot" subtitle="GET /api/v1/analysis/snapshot?ticker=…" action={<button className="button-secondary" type="button" onClick={loadSnapshot} disabled={snapshotLoading || !ticker.trim()}>{snapshotLoading ? <LoaderCircle size={14} className="animate-spin" /> : <Search size={14} />} Fetch snapshot</button>}>
      {snapshotError && <StatePanel mode="error" error={snapshotError} onRetry={loadSnapshot} />}
      {!snapshot && !snapshotLoading && !snapshotError && <StatePanel mode="empty" title="No separate snapshot loaded" description="The analysis response already contains market_data. Use this control to request the dedicated snapshot endpoint." />}
      {snapshotLoading && <StatePanel mode="loading" title="Fetching market snapshot" />}
      {snapshot && <>
        <div className="mb-4 flex flex-wrap items-center gap-2"><h3 className="text-sm font-semibold text-primaryText">{snapshot.company_name ?? snapshot.ticker}</h3><StatusBadge value={snapshot.ticker} />{snapshot.industry && <span className="text-xs text-secondaryText">{snapshot.industry}</span>}</div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">{snapshotFields.map(({ key, label, currency, percent }) => {
          const raw = snapshot[key];
          const display = currency ? formatCurrency(raw, snapshot.currency ?? 'USD') : percent && typeof raw === 'number' ? `${raw}%` : safeText(raw);
          return <div className="rounded-lg border border-line bg-canvas/40 p-3" key={key}><p className="metric-label">{label}</p><p className="mt-2 font-mono text-sm font-medium text-primaryText">{display}</p></div>;
        })}</div>
        <p className="mt-3 text-[11px] text-mutedText">Only fields defined in MarketSnapshot are shown; unavailable values remain blank.</p>
      </>}
    </Panel>
    <div className="flex items-start gap-2 rounded-lg border border-warning/20 bg-warning/5 px-4 py-3 text-xs leading-5 text-secondaryText"><ShieldAlert size={15} className="mt-0.5 shrink-0 text-warning" /><p>The API contract supplied for this frontend describes investment analysis and projections. It does not document a dedicated historical prediction-detail endpoint or evaluation submission route, so this screen does not claim prediction confidence or actual-vs-predicted evaluation when those values are absent.</p></div>
  </div>;
}
