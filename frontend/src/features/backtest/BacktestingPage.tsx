import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { CalendarClock, Info, LoaderCircle, Play, Sparkles } from 'lucide-react';
import { ApiError, api } from '../../api/client';
import type { AnalysedTicker, BacktestRangeJob, BacktestRangeRequest, BacktestRequest, JsonRecord } from '../../api/types';
import { useApiQuery } from '../../hooks/useApiQuery';
import { useJob } from '../../hooks/useJob';
import BacktestJobProgress from './BacktestJobProgress';
import { asRecords, extractRows, isRecord, safeText } from '../../lib/format';
import Panel from '../../components/ui/Panel';
import StatePanel from '../../components/ui/StatePanel';
import AutoChart from '../../components/ui/AutoChart';
import DynamicTable from '../../components/ui/DynamicTable';
import StatusBadge from '../../components/ui/StatusBadge';

type BacktestMode = 'single' | 'range';

export default function BacktestingPage() {
  const [mode, setMode] = useState<BacktestMode>('range');
  const [ticker, setTicker] = useState('');
  const [date, setDate] = useState('2025-01-15');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2025-01-01');
  const [intervalDays, setIntervalDays] = useState('30');
  const [budget, setBudget] = useState('10000');
  const [horizon, setHorizon] = useState('1m');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [result, setResult] = useState<JsonRecord | null>(null);
  const [finishedAt, setFinishedAt] = useState<Date | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  // Range backtests run as API background jobs (one AI call per date)
  const rangeJob = useJob<BacktestRangeJob>('fintrac.backtest-range-job');
  const jobRunning = rangeJob.running;
  const analysedLoader = useCallback(() => api.analysedTickers(), []);
  const analysed = useApiQuery<AnalysedTicker[]>(analysedLoader);
  const analysedBySector = useMemo(() => {
    const groups = new Map<string, AnalysedTicker[]>();
    for (const item of analysed.data ?? []) {
      const sector = item.sector ?? 'Unknown';
      groups.set(sector, [...(groups.get(sector) ?? []), item]);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [analysed.data]);

  useEffect(() => {
    const job = rangeJob.job;
    if (!job) return;
    if (job.status === 'completed' && job.result) {
      setResult(job.result as unknown as JsonRecord);
      setFinishedAt(job.finished_at ? new Date(job.finished_at) : new Date());
    } else if (job.status === 'failed') {
      setError(new Error(job.error ?? 'Backtest job failed'));
    }
  }, [rangeJob.job]);

  const numericBudget = Number(budget);
  const interval = Number(intervalDays);
  const fieldError = useMemo(() => {
    if (!ticker.trim()) return 'A ticker is required.';
    if (!Number.isFinite(numericBudget) || numericBudget <= 0) return 'Budget must be greater than zero.';
    if (mode === 'range') {
      if (!startDate || !endDate) return 'Start and end dates are required.';
      if (startDate > endDate) return 'Start date must not be after end date.';
      if (!Number.isInteger(interval) || interval < 7 || interval > 365) return 'Interval must be between 7 and 365 days.';
    } else if (!date) return 'A historical date is required.';
    return null;
  }, [ticker, numericBudget, mode, startDate, endDate, interval, date]);

  async function runBacktest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (fieldError) return;
    setLoading(true); setError(null); setResult(null); setFinishedAt(null);
    try {
      if (mode === 'range') {
        // Returns immediately; progress and results arrive by polling the job
        const started = await api.startBacktestRangeJob({ ticker: ticker.trim().toUpperCase(), start_date: startDate, end_date: endDate, interval_days: interval, budget: numericBudget, horizon } satisfies BacktestRangeRequest);
        rangeJob.track(started);
        return;
      }
      const response = await api.backtestSingle({ ticker: ticker.trim().toUpperCase(), date, budget: numericBudget, horizon } satisfies BacktestRequest);
      setResult(response);
      setFinishedAt(new Date());
    } catch (reason) { setError(reason instanceof Error ? reason : new Error('Backtest failed')); }
    finally { setLoading(false); }
  }

  const rowData = result ? extractRows(result) : [];
  const errorMessage = error instanceof ApiError && error.status === 0 ? `${error.message}. A single-date run calls the AI once and can take a few minutes; check API logs before resubmitting if the request timed out.` : error?.message;

  return <div className="page-stack">
    <div className="page-intro"><div><p className="eyebrow">HISTORICAL VALIDATION</p><h2 className="page-title">Backtesting</h2><p className="page-description">Run single-date or interval-based historical tests using the documented analysis endpoints.</p></div></div>
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[.8fr_1.35fr]">
      <Panel title="Backtest configuration" subtitle="Requests may call the AI and can be long-running">
        <div className="mb-4 grid grid-cols-2 rounded-lg border border-line bg-canvas p-1"><button type="button" className={`rounded-md px-3 py-2 text-sm ${mode === 'single' ? 'bg-raised font-medium text-primaryText' : 'text-secondaryText'}`} onClick={() => { setMode('single'); setError(null); }}>Single date</button><button type="button" className={`rounded-md px-3 py-2 text-sm ${mode === 'range' ? 'bg-raised font-medium text-primaryText' : 'text-secondaryText'}`} onClick={() => { setMode('range'); setError(null); }}>Date range</button></div>
        <form id="backtest-submit-form" className="space-y-4" onSubmit={runBacktest}>
          <label className="form-label">Asset ticker<input className="input-control mt-2 font-mono uppercase" value={ticker} onChange={(event) => setTicker(event.target.value.toUpperCase())} minLength={1} maxLength={20} required placeholder="Enter a ticker" /></label>
          {analysedBySector.length > 0 && <div><p className="text-[11px] font-medium uppercase tracking-wide text-mutedText">Previously analysed</p><div className="mt-2 max-h-40 space-y-2 overflow-y-auto pr-1">{analysedBySector.map(([sector, items]) => <div key={sector}><p className="text-[11px] text-secondaryText">{sector}</p><div className="mt-1 flex flex-wrap gap-1.5">{items.map((item) => <button type="button" key={item.ticker} title={`${item.analyses} ${item.analyses === 1 ? 'analysis' : 'analyses'}`} className={`rounded-md border px-2 py-0.5 font-mono text-xs ${ticker === item.ticker ? 'border-accent text-accent' : 'border-line text-secondaryText hover:text-primaryText'}`} onClick={() => setTicker(item.ticker)}>{item.ticker}</button>)}</div></div>)}</div></div>}
          {mode === 'single' ? <label className="form-label">Historical date<input className="input-control mt-2" type="date" value={date} onChange={(event) => setDate(event.target.value)} required /></label> : <>
            <div className="grid grid-cols-2 gap-3"><label className="form-label">Start date<input className="input-control mt-2" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required /></label><label className="form-label">End date<input className="input-control mt-2" type="date" value={endDate} min={startDate} onChange={(event) => setEndDate(event.target.value)} required /></label></div>
            <label className="form-label">Interval (days)<input className="input-control mt-2" type="number" min={7} max={365} step={1} value={intervalDays} onChange={(event) => setIntervalDays(event.target.value)} required /><span className="mt-1 block text-[11px] text-mutedText">Allowed by API: 7–365 days</span></label>
          </>}
          <label className="form-label">Budget<input className="input-control mt-2 font-mono" type="number" min="0.01" step="any" value={budget} onChange={(event) => setBudget(event.target.value)} required /></label>
          <label className="form-label">Horizon<select className="input-control mt-2" value={horizon} onChange={(event) => setHorizon(event.target.value)}><option value="1m">1 month</option><option value="3m">3 months</option><option value="6m">6 months</option><option value="1y">1 year</option></select><span className="mt-1 block text-[11px] text-mutedText">The API accepts a string; available values beyond these examples may be backend-supported.</span></label>
          {mode === 'range' && <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs leading-5 text-secondaryText"><Info size={15} className="mt-0.5 shrink-0 text-warning" /><p>Each date is one AI call, so a 12-month range at 30-day intervals is about 12 calls and often 10+ minutes. It runs on the API in the background with live progress — you can leave this page and come back.</p></div>}
          {fieldError && <p className="text-xs text-warning" role="status">{fieldError}</p>}
          <button type="submit" className="button-primary w-full justify-center" disabled={loading || jobRunning || Boolean(fieldError)}>{loading || jobRunning ? <LoaderCircle size={15} className="animate-spin" /> : <Play size={15} />}{loading ? 'Starting…' : jobRunning ? 'Range backtest running…' : 'Run backtest'}</button>
          {error && <StatePanel mode="error" error={error} onRetry={() => { const form = document.getElementById('backtest-submit-form'); if (form instanceof HTMLFormElement) form.requestSubmit(); }} title="Backtest request failed" description={errorMessage} />}
        </form>
      </Panel>

      <div className="space-y-4">
        <Panel title="Backtest result" subtitle={finishedAt ? `Response received ${finishedAt.toLocaleString()}` : 'Results appear after a successful API response'} action={result && <StatusBadge value="Response received" />}>
          {rangeJob.job && (jobRunning || !result) && <BacktestJobProgress job={rangeJob.job} running={jobRunning} pollError={rangeJob.error} onCancel={rangeJob.cancel} />}
          {!rangeJob.job && rangeJob.error && <StatePanel mode="error" title="Backtest job unavailable" description={rangeJob.error.message} />}
          {loading && mode === 'single' && <StatePanel mode="loading" title="Running historical test…" description="One AI call — this can take a minute or two." />}
          {!loading && !result && !error && !rangeJob.job && !rangeJob.error && <StatePanel mode="empty" title="No backtest results yet" description="Configure an asset and date, then run a backtest. This screen never uses sample performance data." />}
          {result && <>
            <div className="rounded-lg border border-line bg-canvas/50 p-3"><div className="flex items-center gap-2"><Sparkles size={16} className="text-accent" /><p className="text-sm font-medium text-primaryText">Result payload received</p></div><p className="mt-2 text-xs leading-5 text-secondaryText">The current OpenAPI response is a generic object. Result metrics and field labels are detected from the response rather than assumed.</p></div>
            {Object.keys(result).length > 0 && <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">{Object.entries(result).filter(([, value]) => !Array.isArray(value) && !isRecord(value)).slice(0, 8).map(([key, value]) => <div className="rounded-md border border-line p-3" key={key}><p className="metric-label">{key.replace(/_/g, ' ')}</p><p className="mt-2 break-words font-mono text-sm text-primaryText">{safeText(value)}</p></div>)}</div>}
            <button type="button" className="mt-3 text-xs font-medium text-accent" onClick={() => setShowRaw((value) => !value)}>{showRaw ? 'Hide full response' : 'Inspect full response JSON'}</button>
            {showRaw && <pre className="mt-3 max-h-64 overflow-auto rounded-lg border border-line bg-canvas p-3 text-xs leading-5 text-secondaryText">{JSON.stringify(result, null, 2)}</pre>}
          </>}
        </Panel>
        {result && <>
          <Panel title="Accuracy / performance curve" subtitle="Rendered only when the response contains a recognizable numeric series"><AutoChart value={result} title="Backtest performance" preferredYKeys={['accuracy', 'equity', 'portfolio_value', 'return_pct', 'value', 'score']} /></Panel>
          <Panel title="Result records" subtitle="Columns inferred from nested response rows"><DynamicTable rows={asRecords(rowData)} emptyTitle="No recognizable result rows" emptyDescription="The generic response did not contain a nested array of row objects. Inspect the full response JSON to identify the contract needed for richer rendering." /></Panel>
        </>}
      </div>
    </div>
    <div className="flex items-start gap-2 rounded-lg border border-line bg-panel px-4 py-3 text-xs leading-5 text-secondaryText"><CalendarClock size={15} className="mt-0.5 shrink-0 text-mutedText" /><p>Backtests use the backend's historical AI predictions and observed outcomes as returned. The frontend does not extrapolate unreturned equity curves, accuracy metrics, or evaluation records.</p></div>
  </div>;
}
