import { useCallback, useState } from 'react';
import { CheckCircle2, Play, ShieldCheck } from 'lucide-react';
import { ApiError, api } from '../../api/client';
import type { JsonRecord } from '../../api/types';
import { asRecords, humanizeKey, safeText } from '../../lib/format';
import { useApiQuery } from '../../hooks/useApiQuery';
import Panel from '../../components/ui/Panel';
import DynamicTable from '../../components/ui/DynamicTable';
import AutoChart from '../../components/ui/AutoChart';
import StatePanel from '../../components/ui/StatePanel';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import CalibrationQualityPanel from './CalibrationQualityPanel';

export default function CalibrationPage() {
  const summaryLoader = useCallback(() => api.calibrationSummary(), []);
  const profilesLoader = useCallback(() => api.calibrationProfiles(), []);
  const confidenceLoader = useCallback(() => api.confidenceCalibration(), []);
  const sectorLoader = useCallback(() => api.accuracyBySector(), []);
  const metricsLoader = useCallback(() => api.calibrationMetrics(), []);
  const summary = useApiQuery(summaryLoader);
  const profiles = useApiQuery(profilesLoader);
  const confidence = useApiQuery(confidenceLoader);
  const sectors = useApiQuery(sectorLoader);
  const metrics = useApiQuery(metricsLoader);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const [triggerSuccess, setTriggerSuccess] = useState<string | null>(null);
  const [triggerResponse, setTriggerResponse] = useState<JsonRecord | null>(null);

  function refreshAll() { summary.refresh(); profiles.refresh(); confidence.refresh(); sectors.refresh(); metrics.refresh(); }

  async function trigger() {
    setTriggerLoading(true); setTriggerError(null); setTriggerSuccess(null); setTriggerResponse(null);
    try {
      const response = await api.triggerCalibration();
      setTriggerResponse(response);
      setTriggerSuccess('The calibration trigger request succeeded. The endpoint response does not establish whether the run has completed.');
      setConfirmOpen(false);
      refreshAll();
    } catch (reason) {
      setConfirmOpen(false);
      const error = reason instanceof Error ? reason : new Error('Calibration trigger failed');
      if (error instanceof ApiError && error.status === 0) setTriggerError('The request outcome is unconfirmed because the connection failed or timed out. Check the latest calibration status before retrying to avoid starting a duplicate run.');
      else setTriggerError(error.message);
    } finally { setTriggerLoading(false); }
  }

  const summaryEntries = summary.data && typeof summary.data === 'object' ? Object.entries(summary.data) : [];
  const profileRows = asRecords(profiles.data);
  const sectorRows = asRecords(sectors.data);
  const confidenceRows = asRecords(confidence.data);

  return <div className="page-stack">
    <div className="page-intro"><div><p className="eyebrow">MODEL GOVERNANCE</p><h2 className="page-title">Calibration dashboard</h2><p className="page-description">Inspect available calibration state, confidence calibration, and sector-level accuracy without inventing missing bias measurements.</p></div><button className="button-secondary" type="button" onClick={refreshAll}><ShieldCheck size={14} /> Refresh all</button></div>

    <Panel title="Calibration system summary" subtitle="GET /api/v1/dashboard/calibration-summary" onRefresh={summary.refresh} loading={summary.loading} action={<button className="button-primary" type="button" onClick={() => { setTriggerError(null); setTriggerSuccess(null); setConfirmOpen(true); }} disabled={triggerLoading}><Play size={14} /> Run calibration</button>}>
      {summary.loading && !summary.data ? <StatePanel mode="loading" title="Loading calibration summary" /> : summary.error && !summary.data ? <StatePanel mode="error" error={summary.error} onRetry={summary.refresh} /> : summaryEntries.length ? <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">{summaryEntries.map(([key, value]) => <div className="rounded-lg border border-line bg-canvas/40 p-3" key={key}><p className="metric-label">{humanizeKey(key)}</p><p className="mt-2 break-words text-sm font-medium text-primaryText">{safeText(value)}</p></div>)}</div> : <StatePanel mode={summary.data ? 'empty' : 'unavailable'} title="No summary fields returned" />}
      {triggerSuccess && <div className="mt-4 flex items-start gap-2 rounded-lg border border-gain/30 bg-gain/10 p-3 text-sm text-gain" role="status"><CheckCircle2 size={16} className="mt-0.5 shrink-0" /><div><p>{triggerSuccess}</p>{triggerResponse && <details className="mt-2"><summary className="cursor-pointer text-xs">Inspect trigger response</summary><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-xs text-secondaryText">{JSON.stringify(triggerResponse, null, 2)}</pre></details>}</div></div>}
      {triggerError && <div className="mt-4 rounded-lg border border-loss/30 bg-loss/10 p-3 text-sm text-loss" role="alert"><p className="font-medium">Calibration trigger status requires attention</p><p className="mt-1 leading-5">{triggerError}</p></div>}
    </Panel>

    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Panel title="Confidence calibration" subtitle="GET /api/v1/dashboard/confidence-calibration" onRefresh={confidence.refresh} loading={confidence.loading}>
        {confidence.loading && !confidence.data ? <StatePanel mode="loading" title="Loading confidence calibration" /> : confidence.error && !confidence.data ? <StatePanel mode="error" error={confidence.error} onRetry={confidence.refresh} /> : confidence.data ? <AutoChart value={confidenceRows} title="Confidence calibration" preferredYKeys={['accuracy_pct', 'accuracy', 'actual_accuracy', 'confidence', 'count', 'value']} /> : <StatePanel mode="unavailable" title="Confidence calibration unavailable" />}
        <p className="mt-2 text-xs leading-5 text-secondaryText">Uses the confidence shown to users (after correction). The calibration quality panel below compares it with the model's raw confidence.</p>
      </Panel>
      <Panel title="Accuracy by sector" subtitle="GET /api/v1/dashboard/accuracy-by-sector" onRefresh={sectors.refresh} loading={sectors.loading}>
        {sectors.loading && !sectors.data ? <StatePanel mode="loading" title="Loading sector accuracy" /> : sectors.error && !sectors.data ? <StatePanel mode="error" error={sectors.error} onRetry={sectors.refresh} /> : <DynamicTable rows={sectorRows} emptyTitle="No sector accuracy records" emptyDescription="The endpoint returned no rows to compare." maxColumns={6} />}
      </Panel>
    </div>

    <Panel title="Active calibration profiles" subtitle="GET /api/v1/dashboard/calibration-profiles" onRefresh={profiles.refresh} loading={profiles.loading}>
      {profiles.loading && !profiles.data ? <StatePanel mode="loading" title="Loading calibration profiles" /> : profiles.error && !profiles.data ? <StatePanel mode="error" error={profiles.error} onRetry={profiles.refresh} /> : <DynamicTable rows={profileRows} maxColumns={7} emptyTitle="No calibration profiles returned" emptyDescription="The backend did not return any profile records. No synthetic correction factors are displayed." />}
    </Panel>

    <CalibrationQualityPanel query={metrics} />

    <ConfirmDialog open={confirmOpen} title="Run calibration?" description="This sends POST /api/v1/dashboard/trigger-calibration without a request body. The API contract does not establish whether the run is synchronous or how duplicate runs are handled. Confirm only when you intend to invoke the backend action." confirmLabel="Confirm and run" loading={triggerLoading} onCancel={() => setConfirmOpen(false)} onConfirm={() => { void trigger(); }} />
  </div>;
}
