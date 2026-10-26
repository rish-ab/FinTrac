import { useMemo } from 'react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { JsonRecord } from '../../api/types';
import { extractRows, humanizeKey, safeText } from '../../lib/format';
import StatePanel from './StatePanel';

interface AutoChartProps { value: unknown; title?: string; preferredYKeys?: string[]; }

function selectNumericKey(rows: JsonRecord[], preferred: string[]): string | undefined {
  const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  for (const target of preferred) {
    const exact = keys.find((key) => key.toLowerCase() === target.toLowerCase());
    if (exact && rows.some((row) => typeof row[exact] === 'number')) return exact;
  }
  return keys.find((key) => rows.filter((row) => typeof row[key] === 'number').length >= Math.min(2, rows.length));
}

function selectXKey(rows: JsonRecord[]): string | undefined {
  const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  const preferred = ['date', 'day', 'timestamp', 'created_at', 'time', 'period', 'x', 'label'];
  for (const target of preferred) {
    const key = keys.find((candidate) => candidate.toLowerCase() === target);
    if (key && rows.some((row) => row[key] !== undefined && row[key] !== null)) return key;
  }
  return keys.find((key) => rows.some((row) => typeof row[key] === 'string'));
}

export default function AutoChart({ value, title = 'API time series', preferredYKeys = ['accuracy', 'hit_rate', 'count', 'value', 'score'] }: AutoChartProps) {
  const model = useMemo(() => {
    const rows = extractRows(value);
    if (!rows.length) return null;
    const xKey = selectXKey(rows);
    const yKey = selectNumericKey(rows, preferredYKeys);
    if (!xKey || !yKey) return null;
    const data = rows.map((row) => ({ label: safeText(row[xKey]), value: typeof row[yKey] === 'number' ? row[yKey] : null })).filter((row) => row.value !== null);
    return data.length ? { xKey, yKey, data } : null;
  }, [value, preferredYKeys]);

  if (!model) return <StatePanel mode="unavailable" title="Chart series unavailable" description="The API did not return a recognizable series with a category and numeric measure. No chart values have been fabricated." />;
  return (
    <div className="w-full" role="img" aria-label={`${title}: ${humanizeKey(model.yKey)} over ${humanizeKey(model.xKey)}`}>
      <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={model.data} margin={{ top: 10, right: 12, left: -4, bottom: 2 }}>
          <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={28} />
          <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} width={42} />
          <Tooltip contentStyle={{ background: 'var(--tooltip-bg)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text-primary)', fontSize: 12 }} labelStyle={{ color: 'var(--text-secondary)' }} formatter={(v) => [safeText(v), humanizeKey(model.yKey)]} />
          <Line type="monotone" dataKey="value" stroke="#a3e635" strokeWidth={2} dot={false} activeDot={{ r: 4, fill: '#a3e635', stroke: '#0b0f14' }} connectNulls={false} />
        </LineChart>
      </ResponsiveContainer>
      </div>
      <p className="mt-1 text-[11px] text-mutedText">Series inferred from API keys: {humanizeKey(model.yKey)} by {humanizeKey(model.xKey)}.</p>
    </div>
  );
}
