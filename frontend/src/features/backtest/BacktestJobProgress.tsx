import { useState } from 'react';
import { CircleStop, LoaderCircle } from 'lucide-react';
import type { BacktestPoint, BacktestRangeJob } from '../../api/types';
import StatusBadge from '../../components/ui/StatusBadge';

interface BacktestJobProgressProps {
  job: BacktestRangeJob;
  running: boolean;
  pollError: Error | null;
  onCancel: () => Promise<void>;
}

function duration(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(s / 60);
  return m ? `${m}m ${String(s % 60).padStart(2, '0')}s` : `${s}s`;
}

function outcome(point: BacktestPoint): { label: string; tone: string } {
  if (point.error) return { label: 'Error', tone: 'border-loss/30 bg-loss/10 text-loss' };
  if (point.direction_correct === true) return { label: 'Correct', tone: 'border-gain/30 bg-gain/10 text-gain' };
  if (point.direction_correct === false) return { label: 'Wrong', tone: 'border-loss/30 bg-loss/10 text-loss' };
  return { label: 'Not yet known', tone: 'border-line bg-raised text-secondaryText' };
}

export default function BacktestJobProgress({ job, running, pollError, onCancel }: BacktestJobProgressProps) {
  const [cancelling, setCancelling] = useState(false);
  const { done, total, message } = job.progress;
  const pct = total ? Math.round((done / total) * 100) : null;

  // ETA from the average time per finished step (each step is one LLM call)
  const started = job.started_at ? new Date(job.started_at).getTime() : null;
  const elapsed = started ? (job.finished_at ? new Date(job.finished_at).getTime() : Date.now()) - started : 0;
  const eta = running && started && done > 0 && total ? (elapsed / done) * (total - done) : null;

  async function cancel() {
    setCancelling(true);
    try { await onCancel(); } finally { setCancelling(false); }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-line bg-canvas/50 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {running && <LoaderCircle size={16} className="animate-spin text-accent" />}
            <StatusBadge value={job.status} />
            <span className="text-sm text-secondaryText">{job.status === 'queued' ? 'Waiting for the AI — another backtest is running' : message}</span>
          </div>
          {running && (
            <button type="button" className="button-secondary" onClick={() => { void cancel(); }} disabled={cancelling}>
              <CircleStop size={14} /> {cancelling ? 'Cancelling…' : 'Cancel'}
            </button>
          )}
        </div>

        <div
          className="mt-4 h-2 w-full overflow-hidden rounded-full bg-raised"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total ?? undefined}
          aria-valuenow={done}
          aria-label="Backtest progress"
        >
          <div
            className={`h-full rounded-full transition-all duration-500 ${job.status === 'failed' ? 'bg-loss' : job.status === 'cancelled' ? 'bg-warning' : 'bg-accent'}`}
            style={{ width: pct === null ? '0%' : `${pct}%` }}
          />
        </div>

        <div className="mt-2 flex flex-wrap justify-between gap-2 font-mono text-xs text-secondaryText">
          <span>{total ? `${done} / ${total} dates` : 'Preparing dates…'}{pct !== null && ` · ${pct}%`}</span>
          <span>
            {started ? `elapsed ${duration(elapsed)}` : 'not started'}
            {eta !== null && ` · ~${duration(eta)} left`}
          </span>
        </div>

        {running && (
          <p className="mt-3 text-xs leading-5 text-mutedText">
            Runs on the API in the background — you can leave this page and come back. Each date is one AI call.
            Cancelling stops after the date currently in progress.
          </p>
        )}
        {job.status === 'failed' && job.error && <p className="mt-3 text-sm text-loss" role="alert">{job.error}</p>}
        {pollError && <p className="mt-3 text-xs text-warning" role="status">{pollError.message}</p>}
      </div>

      {job.partial.length > 0 && (
        <div className="table-wrap">
          <table className="data-table whitespace-nowrap">
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Verdict</th>
                <th scope="col" className="text-right">Confidence</th>
                <th scope="col" className="text-right">Actual return</th>
                <th scope="col">Outcome</th>
              </tr>
            </thead>
            <tbody>
              {job.partial.map((point) => (
                <tr key={point.backtest_date}>
                  <td className="font-mono">{point.backtest_date}</td>
                  <td className="font-mono">{point.ai_verdict ?? '—'}</td>
                  <td className="text-right font-mono tabular-nums">
                    {typeof point.ai_confidence === 'number' ? `${Math.round(point.ai_confidence * 100)}%` : '—'}
                  </td>
                  <td className="text-right font-mono tabular-nums">
                    {typeof point.actual_return_pct === 'number' ? `${point.actual_return_pct > 0 ? '+' : ''}${point.actual_return_pct.toFixed(2)}%` : '—'}
                  </td>
                  <td title={point.error ?? undefined}>
                    <span className={`status-badge ${outcome(point).tone}`}>{outcome(point).label}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
