interface StatusBadgeProps { value: string; }

export default function StatusBadge({ value }: StatusBadgeProps) {
  const lower = value.toLowerCase();
  let tone = 'border-line bg-raised text-secondaryText';
  if (/(evaluated|active|success|sent|complete|healthy|positive)/.test(lower)) tone = 'border-gain/30 bg-gain/10 text-gain';
  else if (/(pending|proposed|testing|warning|stale|unknown|unverified)/.test(lower)) tone = 'border-warning/30 bg-warning/10 text-warning';
  else if (/(failed|error|retired|negative|loss|disabled)/.test(lower)) tone = 'border-loss/30 bg-loss/10 text-loss';
  return <span className={`status-badge ${tone}`}>{value}</span>;
}
