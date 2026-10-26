import type { ReactNode } from 'react';

interface MetricCardProps {
  label: string;
  value: ReactNode;
  detail?: string;
  icon?: ReactNode;
  tone?: 'default' | 'positive' | 'negative' | 'warning';
}

export default function MetricCard({ label, value, detail, icon, tone = 'default' }: MetricCardProps) {
  const valueTone = tone === 'positive' ? 'text-gain' : tone === 'negative' ? 'text-loss' : tone === 'warning' ? 'text-warning' : 'text-primaryText';
  return (
    <div className="metric-card">
      <div className="flex items-start justify-between gap-3">
        <span className="metric-label">{label}</span>
        {icon && <span className="rounded-md border border-line bg-raised p-2 text-secondaryText">{icon}</span>}
      </div>
      <div className={`mt-3 truncate font-mono text-2xl font-semibold tracking-tight ${valueTone}`}>{value}</div>
      {detail && <p className="mt-2 text-xs leading-5 text-secondaryText">{detail}</p>}
    </div>
  );
}
