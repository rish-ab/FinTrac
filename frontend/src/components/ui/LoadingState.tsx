interface LoadingStateProps { rows?: number; label?: string; }

export default function LoadingState({ rows = 3, label = 'Loading data' }: LoadingStateProps) {
  return (
    <div className="space-y-3" aria-label={label} aria-busy="true">
      <div className="h-3 w-28 animate-pulse rounded bg-raised" />
      {Array.from({ length: rows }).map((_, index) => <div key={index} className="h-10 animate-pulse rounded-md border border-line/50 bg-raised/60" />)}
      <span className="sr-only">{label}</span>
    </div>
  );
}
