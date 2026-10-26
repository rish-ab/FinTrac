import { useCallback } from 'react';
import { Activity, ArrowUpRight, Clock3, ShieldCheck } from 'lucide-react';
import { api } from '../../api/client';
import type { JsonRecord } from '../../api/types';
import { asRecords, humanizeKey, safeText } from '../../lib/format';
import { useApiQuery } from '../../hooks/useApiQuery';
import Panel from '../../components/ui/Panel';
import MetricCard from '../../components/ui/MetricCard';
import DynamicTable from '../../components/ui/DynamicTable';
import AutoChart from '../../components/ui/AutoChart';
import StatePanel from '../../components/ui/StatePanel';

function MetricsBody({ value }: { value: unknown }) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return <StatePanel mode="unavailable" title="Metrics not available" description="The dashboard metrics response did not contain a JSON object." />;
  const entries = Object.entries(value as JsonRecord);
  if (!entries.length) return <StatePanel mode="empty" title="No metric fields returned" />;
  return <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">{entries.slice(0, 8).map(([key, val]) => <MetricCard key={key} label={humanizeKey(key)} value={safeText(val)} detail="Value as returned by API" />)}</div>;
}

interface DashboardPageProps { onOpenAnalysis: (ticker?: string) => void; }

export default function DashboardPage({ onOpenAnalysis }: DashboardPageProps) {
  const metricsLoader = useCallback(() => api.dashboardMetrics(), []);
  const predictionsLoader = useCallback(() => api.recentPredictions(20), []);
  const timelineLoader = useCallback(() => api.predictionTimeline(30), []);
  const calibrationLoader = useCallback(() => api.calibrationSummary(), []);
  const metrics = useApiQuery(metricsLoader);
  const predictions = useApiQuery(predictionsLoader);
  const timeline = useApiQuery(timelineLoader);
  const calibration = useApiQuery(calibrationLoader);
  const rows = asRecords(predictions.data);

  function rowToAnalysis(row: JsonRecord) {
    const ticker = [row.ticker, row.symbol, row.asset].find((item) => typeof item === 'string');
    onOpenAnalysis(typeof ticker === 'string' ? ticker : undefined);
  }

  return <div className="page-stack">
    <div className="page-intro"><div><p className="eyebrow">SYSTEM OVERVIEW</p><h2 className="page-title">Dashboard</h2><p className="page-description">A live view of model activity, evaluation coverage, and calibration signals.</p></div><div className="flex items-center gap-2"><span className="inline-flex items-center gap-2 rounded-md border border-line bg-panel px-3 py-2 text-xs text-secondaryText"><span className="h-1.5 w-1.5 rounded-full bg-mutedText" /> Live API data</span><button className="button-secondary" type="button" onClick={() => { metrics.refresh(); predictions.refresh(); timeline.refresh(); calibration.refresh(); }}><Activity size={14} /> Refresh all</button></div></div>

    {metrics.error && <StatePanel mode="error" error={metrics.error} onRetry={metrics.refresh} title="Overall metrics unavailable" />}
    {metrics.loading && !metrics.data ? <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">{[1,2,3,4].map((item) => <div className="metric-card h-28 animate-pulse" key={item}><div className="h-3 w-24 rounded bg-raised" /><div className="mt-5 h-7 w-20 rounded bg-raised" /></div>)}</div> : metrics.data ? <MetricsBody value={metrics.data} /> : <div className="grid grid-cols-2 gap-3 xl:grid-cols-4"><MetricCard label="Overall metrics" value="Unavailable" detail="No successful API response" /></div>}

    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.55fr_1fr]">
      <Panel title="Prediction timeline" subtitle="Daily prediction counts and accuracy over the selected period" onRefresh={timeline.refresh} loading={timeline.loading}>
        {timeline.loading && !timeline.data ? <StatePanel mode="loading" title="Loading timeline" /> : timeline.error && !timeline.data ? <StatePanel mode="error" error={timeline.error} onRetry={timeline.refresh} /> : timeline.data ? <AutoChart value={timeline.data} title="Prediction timeline" preferredYKeys={['accuracy', 'prediction_count', 'count', 'total_predictions']} /> : <StatePanel mode="unavailable" title="Timeline unavailable" />}
      </Panel>
      <Panel title="Calibration health" subtitle="Current calibration summary and profile availability" onRefresh={calibration.refresh} loading={calibration.loading}>
        {calibration.loading && !calibration.data ? <StatePanel mode="loading" title="Loading calibration status" /> : calibration.error && !calibration.data ? <StatePanel mode="error" error={calibration.error} onRetry={calibration.refresh} /> : calibration.data ? <div className="space-y-3">{Object.entries(calibration.data as JsonRecord).slice(0, 8).map(([key, value]) => <div className="flex items-start justify-between gap-4 border-b border-line/70 pb-3 last:border-0 last:pb-0" key={key}><span className="text-xs text-secondaryText">{humanizeKey(key)}</span><span className="max-w-[60%] text-right text-sm font-medium text-primaryText">{safeText(value)}</span></div>)}</div> : <StatePanel mode="unavailable" title="Calibration summary unavailable" />}
      </Panel>
    </div>

    <Panel title="Recent predictions" subtitle="Fields shown are taken from the returned API records" action={<button className="text-xs font-medium text-accent hover:text-lime-300" type="button" onClick={() => onOpenAnalysis()}>Open analysis <ArrowUpRight size={13} className="inline" /></button>} onRefresh={predictions.refresh} loading={predictions.loading}>
      {predictions.loading && !predictions.data ? <StatePanel mode="loading" title="Loading recent predictions" /> : predictions.error && !predictions.data ? <StatePanel mode="error" error={predictions.error} onRetry={predictions.refresh} /> : <DynamicTable rows={rows} maxColumns={7} emptyTitle="No recent prediction records" emptyDescription="The endpoint returned no rows. The frontend does not insert sample predictions." onRowClick={rowToAnalysis} />}
    </Panel>

    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Panel title="Confidence calibration" subtitle="Accuracy by reported confidence bucket">
        <button className="button-secondary w-full justify-center" type="button" onClick={() => window.dispatchEvent(new CustomEvent('fintrac:navigate', { detail: 'calibration' }))}><ShieldCheck size={14} /> Inspect calibration</button>
        <p className="mt-3 text-xs leading-5 text-secondaryText">The dedicated confidence-calibration endpoint is used on the Calibration screen. No calibration score is inferred here.</p>
      </Panel>
      <Panel title="Model attribution" subtitle="Highest-scored attributions from the API">
        <p className="text-sm text-secondaryText">Attribution records are available through the documented endpoint and will be rendered when loaded in the detail view.</p>
      </Panel>
      <Panel title="Evaluation coverage" subtitle="Evaluation status must be present in model data">
        <div className="flex items-center gap-3"><Clock3 size={18} className="text-mutedText" /><p className="text-sm leading-6 text-secondaryText">Pending versus evaluated counts are not fabricated when the metrics response does not define those fields.</p></div>
      </Panel>
    </div>
  </div>;
}
