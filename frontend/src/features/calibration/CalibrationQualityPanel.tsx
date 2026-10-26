import { useState } from 'react';
import { Hourglass } from 'lucide-react';
import type { CalibrationMetrics, RateWithInterval, ReliabilityBucket } from '../../api/types';
import type { QueryState } from '../../hooks/useApiQuery';
import Panel from '../../components/ui/Panel';
import MetricCard from '../../components/ui/MetricCard';
import StatePanel from '../../components/ui/StatePanel';

const pct = (x: number | null | undefined) => (x == null ? '—' : `${(x * 100).toFixed(1)}%`);
const ciText = (ci: [number, number]) => `${Math.round(ci[0] * 100)}–${Math.round(ci[1] * 100)}%`;
const num = (x: number | null | undefined) => (x == null ? '—' : x.toFixed(3));

// Brier/ECE: lower is better. Compare what users saw (corrected) with raw.
function correctionDetail(raw?: number | null, shown?: number | null, format: (x: number) => string = (x) => x.toFixed(3)) {
  if (raw == null || shown == null) return undefined;
  if (Math.abs(raw - shown) < 1e-4) return `Shown to users: ${format(shown)} (no correction applied)`;
  return `Shown to users: ${format(shown)} — correction ${shown < raw ? 'improved' : 'worsened'} it`;
}

// ── Reliability diagram ──────────────────────────────────────────────────

const W = 340;
const H = 270;
const PAD = { l: 42, r: 14, t: 16, b: 36 };
const sx = (v: number) => PAD.l + v * (W - PAD.l - PAD.r);
const sy = (v: number) => H - PAD.b - v * (H - PAD.t - PAD.b);

function ReliabilityDiagram({ buckets }: { buckets: ReliabilityBucket[] }) {
  const [hover, setHover] = useState<ReliabilityBucket | null>(null);
  const maxN = Math.max(1, ...buckets.map((b) => b.n));
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full max-w-md" role="img" aria-label="Reliability diagram: observed accuracy against stated confidence, with 95% intervals">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={sx(0)} x2={sx(1)} y1={sy(t)} y2={sy(t)} stroke="var(--chart-grid)" strokeWidth={1} />
            <text x={PAD.l - 6} y={sy(t) + 3} textAnchor="end" fontSize={10} fill="var(--text-muted)" className="font-mono">{t * 100}%</text>
            <text x={sx(t)} y={H - PAD.b + 15} textAnchor="middle" fontSize={10} fill="var(--text-muted)" className="font-mono">{t * 100}%</text>
          </g>
        ))}
        <text x={(sx(0) + sx(1)) / 2} y={H - 4} textAnchor="middle" fontSize={10} fill="var(--text-secondary)">Stated confidence (raw)</text>
        <text x={11} y={(sy(0) + sy(1)) / 2} textAnchor="middle" fontSize={10} fill="var(--text-secondary)" transform={`rotate(-90 11 ${(sy(0) + sy(1)) / 2})`}>Observed accuracy</text>

        {/* Perfect calibration */}
        <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} stroke="var(--text-muted)" strokeWidth={1.5} strokeDasharray="4 4" />

        {buckets.map((b) => {
          const cx = sx(b.mean_confidence);
          const r = 4 + 4 * Math.sqrt(b.n / maxN);
          const active = hover?.bucket === b.bucket;
          return (
            <g key={b.bucket} onMouseEnter={() => setHover(b)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(b)} onBlur={() => setHover(null)} tabIndex={0} aria-label={`Bucket ${b.bucket}: ${b.correct} of ${b.n} correct`}>
              <line x1={cx} x2={cx} y1={sy(b.accuracy_ci[0])} y2={sy(b.accuracy_ci[1])} stroke="var(--series-1)" strokeWidth={2} strokeLinecap="round" opacity={0.5} />
              <circle cx={cx} cy={sy(b.accuracy)} r={active ? r + 1.5 : r} fill="var(--series-1)" stroke="var(--panel)" strokeWidth={2} />
              {/* Generous hit target */}
              <rect x={cx - 14} y={PAD.t} width={28} height={H - PAD.t - PAD.b} fill="transparent" />
            </g>
          );
        })}
      </svg>

      {hover && (
        <div
          className="pointer-events-none absolute top-1 whitespace-nowrap rounded-md border border-line px-2.5 py-2 font-mono text-[11px] leading-5 text-primaryText shadow-panel"
          style={{
            background: 'var(--tooltip-bg)',
            left: `${(sx(hover.mean_confidence) / W) * 100}%`,
            transform: hover.mean_confidence > 0.6 ? 'translateX(-105%)' : 'translateX(10px)',
          }}
        >
          <div className="text-secondaryText">Bucket {hover.bucket}</div>
          <div>Confidence {pct(hover.mean_confidence)}</div>
          <div>Accuracy {pct(hover.accuracy)} <span className="text-secondaryText">({ciText(hover.accuracy_ci)})</span></div>
          <div className="text-secondaryText">{hover.correct}/{hover.n} correct</div>
        </div>
      )}
    </div>
  );
}

// ── Rate table ───────────────────────────────────────────────────────────

function RateTable({ label, rows, baseline }: { label: string; rows: [string, RateWithInterval][]; baseline?: Record<string, number> }) {
  if (!rows.length) return <StatePanel mode="empty" title={`No ${label.toLowerCase()} data`} />;
  return (
    <div className="table-wrap">
      <table className="data-table whitespace-nowrap">
        <thead>
          <tr>
            <th scope="col">{label}</th>
            <th scope="col" className="text-right">n</th>
            <th scope="col" className="text-right">Hit rate</th>
            <th scope="col" className="text-right">95% CI</th>
            {baseline && <th scope="col" className="text-right">Baseline</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map(([key, r]) => {
            const base = baseline?.[key];
            // Skill (or the lack of it) only when the whole interval clears the baseline
            const tone = base == null || !r.n ? 'text-primaryText' : r.ci[0] > base ? 'text-gain' : r.ci[1] < base ? 'text-loss' : 'text-primaryText';
            return (
              <tr key={key}>
                <td className="font-mono text-primaryText">{key}</td>
                <td className="text-right font-mono tabular-nums text-secondaryText">{r.n}</td>
                <td className={`text-right font-mono font-semibold tabular-nums ${tone}`}>{r.n ? pct(r.rate) : '—'}</td>
                <td className="text-right font-mono tabular-nums text-secondaryText">{r.n ? ciText(r.ci) : '—'}</td>
                {baseline && <td className="text-right font-mono tabular-nums text-secondaryText">{base == null ? '—' : pct(base)}</td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Panel ────────────────────────────────────────────────────────────────

export default function CalibrationQualityPanel({ query }: { query: QueryState<CalibrationMetrics> }) {
  const { data, loading, error, refresh } = query;

  let body;
  if (loading && !data) body = <StatePanel mode="loading" title="Loading calibration quality" />;
  else if (error && !data) body = <StatePanel mode="error" error={error} onRetry={refresh} />;
  else if (!data || data.n === 0) body = <StatePanel mode="empty" title="No evaluated predictions yet" description="Calibration quality appears once predictions pass their horizon and are graded. Legacy predictions recorded with already-corrected confidence are excluded." />;
  else {
    const baseline = data.baseline_up_rate != null ? { BUY: data.baseline_up_rate } : undefined;
    body = (
      <div className="space-y-5">
        {!data.enough_data && (
          <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs leading-5 text-secondaryText" role="status">
            <Hourglass size={15} className="mt-0.5 shrink-0 text-warning" />
            <p>Only {data.n} usable evaluated prediction{data.n === 1 ? '' : 's'} so far. Bias corrections stay inactive until there is enough evidence, and the intervals below are wide by design.</p>
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Brier score" value={num(data.brier_raw)} detail={correctionDetail(data.brier_raw, data.brier_shown) ?? 'Squared gap between confidence and outcome. 0 is perfect; 0.25 is a coin flip at 50%.'} />
          <MetricCard label="Calibration error (ECE)" value={pct(data.ece_raw)} detail={correctionDetail(data.ece_raw, data.ece_shown, (x) => `${(x * 100).toFixed(1)}%`) ?? 'Average |accuracy − confidence| across confidence buckets.'} />
          <MetricCard label="Accuracy" value={data.accuracy?.n ? pct(data.accuracy.rate) : '—'} detail={data.accuracy?.n ? `95% interval ${ciText(data.accuracy.ci)}` : undefined} />
          <MetricCard label="Predictions" value={data.n} detail="Unique evaluated calls (repeat queries counted once)" />
        </div>

        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,.85fr)_minmax(0,1.15fr)]">
          <div>
            <p className="mb-2 text-xs leading-5 text-secondaryText">Reliability — points on the dashed line are well calibrated. Whiskers are 95% intervals; larger points have more predictions.</p>
            <ReliabilityDiagram buckets={data.reliability_raw ?? []} />
          </div>
          <div className="min-w-0 space-y-4">
            <div>
              <p className="mb-2 text-xs leading-5 text-secondaryText">By action — BUY shows skill only when its whole interval sits above the baseline (how often the asset went up anyway).</p>
              <RateTable label="Action" rows={Object.entries(data.by_action ?? {})} baseline={baseline} />
            </div>
            <div>
              <p className="mb-2 text-xs leading-5 text-secondaryText">By horizon</p>
              <RateTable label="Horizon" rows={Object.entries(data.by_horizon ?? {})} />
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <Panel
      title="Calibration quality"
      subtitle="GET /api/v1/dashboard/calibration-metrics · raw model confidence vs graded outcomes"
      onRefresh={refresh}
      loading={loading}
      action={data && data.n > 0 && <span className={`status-badge ${data.enough_data ? 'border-gain/30 bg-gain/10 text-gain' : 'border-warning/30 bg-warning/10 text-warning'}`}>{data.enough_data ? 'Sufficient data' : 'Collecting data'}</span>}
    >
      {body}
    </Panel>
  );
}
