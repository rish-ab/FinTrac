import { useCallback, useState } from 'react';
import { GitBranch, LoaderCircle, Play, RefreshCw, Workflow } from 'lucide-react';
import { ApiError, api } from '../../api/client';
import type { JsonRecord } from '../../api/types';
import { asRecords, humanizeKey, safeText } from '../../lib/format';
import { useApiQuery } from '../../hooks/useApiQuery';
import Panel from '../../components/ui/Panel';
import DynamicTable from '../../components/ui/DynamicTable';
import StatePanel from '../../components/ui/StatePanel';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import StatusBadge from '../../components/ui/StatusBadge';

const STAGES = ['proposed', 'testing', 'active', 'retired'];

export default function EvolutionPage() {
  const improvementsLoader = useCallback(() => api.modelImprovements(), []);
  const summaryLoader = useCallback(() => api.improvementSummary(), []);
  const improvements = useApiQuery(improvementsLoader);
  const summary = useApiQuery(summaryLoader);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [triggerResponse, setTriggerResponse] = useState<JsonRecord | null>(null);

  const rows = asRecords(improvements.data);
  const summaryEntries = summary.data && typeof summary.data === 'object' ? Object.entries(summary.data) : [];
  const stages = STAGES.map((stage) => ({ stage, count: rows.filter((row) => String(row.status ?? row.stage ?? '').toLowerCase() === stage).length }));
  const hasStatus = rows.some((row) => typeof row.status === 'string' || typeof row.stage === 'string');

  function refreshAll() { improvements.refresh(); summary.refresh(); }

  async function triggerEvolution() {
    setLoading(true); setError(null); setSuccess(null); setTriggerResponse(null);
    try {
      const response = await api.triggerEvolution();
      setTriggerResponse(response);
      setSuccess('The evolution trigger request succeeded. Review the refreshed lifecycle records to see whether the backend changed prompt stages.');
      setConfirmOpen(false);
      improvements.refresh(); summary.refresh();
    } catch (reason) {
      setConfirmOpen(false);
      const e = reason instanceof Error ? reason : new Error('Evolution trigger failed');
      if (e instanceof ApiError && e.status === 0) setError('The request outcome is unconfirmed because the connection failed or timed out. Check the latest improvement records before retrying.');
      else setError(e.message);
    } finally { setLoading(false); }
  }

  return <div className="page-stack">
    <div className="page-intro"><div><p className="eyebrow">MODEL LIFECYCLE</p><h2 className="page-title">Prompt evolution</h2><p className="page-description">Inspect returned model-improvement records and lifecycle state. Promotion and retirement controls are omitted because no transition endpoints are documented.</p></div><button type="button" className="button-secondary" onClick={refreshAll} disabled={loading}><RefreshCw size={14} /> Refresh</button></div>

    <Panel title="Evolution summary" subtitle="GET /api/v1/dashboard/improvement-summary" onRefresh={summary.refresh} loading={summary.loading} action={<button className="button-primary" type="button" onClick={() => { setError(null); setSuccess(null); setConfirmOpen(true); }} disabled={loading}><Play size={14} /> Trigger evolution</button>}>
      {summary.loading && !summary.data ? <StatePanel mode="loading" title="Loading evolution summary" /> : summary.error && !summary.data ? <StatePanel mode="error" error={summary.error} onRetry={summary.refresh} /> : summaryEntries.length ? <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">{summaryEntries.map(([key, value]) => <div className="rounded-lg border border-line bg-canvas/40 p-3" key={key}><p className="metric-label">{humanizeKey(key)}</p><p className="mt-2 break-words text-sm font-medium text-primaryText">{safeText(value)}</p></div>)}</div> : <StatePanel mode={summary.data ? 'empty' : 'unavailable'} title="No summary fields returned" />}
      {success && <div className="mt-4 rounded-lg border border-gain/30 bg-gain/10 p-3 text-sm text-gain" role="status">{success}{triggerResponse && <details className="mt-2"><summary className="cursor-pointer text-xs">Inspect trigger response</summary><pre className="mt-2 max-h-48 overflow-auto text-xs text-secondaryText">{JSON.stringify(triggerResponse, null, 2)}</pre></details>}</div>}
      {error && <div className="mt-4 rounded-lg border border-loss/30 bg-loss/10 p-3 text-sm text-loss" role="alert">{error}</div>}
    </Panel>

    <Panel title="Lifecycle stages" subtitle="Counts derived only from returned records that expose a matching status field" onRefresh={improvements.refresh} loading={improvements.loading}>
      {improvements.loading && !improvements.data ? <StatePanel mode="loading" title="Loading improvement records" /> : improvements.error && !improvements.data ? <StatePanel mode="error" error={improvements.error} onRetry={improvements.refresh} /> : !hasStatus ? <StatePanel mode="unavailable" title="Lifecycle fields unavailable" description="The response does not expose a recognizable status or stage field, so per-stage counts cannot be computed." /> : <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">{stages.map(({ stage, count }) => <div key={stage} className="rounded-lg border border-line bg-canvas/40 p-4"><div className="flex items-center justify-between gap-2"><StatusBadge value={stage} /><Workflow size={15} className="text-mutedText" /></div><p className="mt-4 font-mono text-2xl font-semibold text-primaryText">{count}</p><p className="mt-1 text-xs text-secondaryText">matching records</p></div>)}</div>}
    </Panel>

    <Panel title="Model-improvement records" subtitle="GET /api/v1/dashboard/model-improvements" onRefresh={improvements.refresh} loading={improvements.loading}>
      {improvements.loading && !improvements.data ? <StatePanel mode="loading" title="Loading model-improvement records" /> : improvements.error && !improvements.data ? <StatePanel mode="error" error={improvements.error} onRetry={improvements.refresh} /> : <DynamicTable rows={rows} maxColumns={8} emptyTitle="No model-improvement records" emptyDescription="The API returned no improvement records. The interface does not invent prompt names or performance metrics." />}
    </Panel>

    <Panel title="Prompt-level performance" subtitle="Requires explicit per-prompt evaluation and metric fields"><div className="flex items-start gap-3 rounded-lg border border-dashed border-line p-4"><GitBranch size={18} className="mt-0.5 text-mutedText" /><div><p className="text-sm font-medium text-primaryText">Performance comparison is schema-dependent</p><p className="mt-1 text-xs leading-5 text-secondaryText">The supplied contract documents improvement lifecycle records and a summary, but not explicit per-prompt hit rate, Brier score, confidence calibration, or causal before/after performance. Any returned record fields will be displayed; unsupported metrics remain unavailable.</p></div></div></Panel>

    <ConfirmDialog open={confirmOpen} title="Trigger prompt evolution?" description="This sends POST /api/v1/dashboard/trigger-evolution with no documented request body. The response schema does not specify whether the run completes synchronously. Confirm to invoke the backend operation." confirmLabel="Confirm and trigger" loading={loading} onCancel={() => setConfirmOpen(false)} onConfirm={() => { void triggerEvolution(); }} />
    {loading && <div className="fixed bottom-20 right-5 flex items-center gap-2 rounded-lg border border-line bg-panel px-4 py-3 text-xs text-secondaryText shadow-panel"><LoaderCircle size={14} className="animate-spin" /> Evolution request in progress</div>}
  </div>;
}
