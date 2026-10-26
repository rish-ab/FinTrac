import { AlertTriangle, Database, RefreshCw, WifiOff } from 'lucide-react';
import { errorTitle } from '../../hooks/useApiQuery';

interface StatePanelProps {
  mode: 'loading' | 'empty' | 'error' | 'unavailable';
  error?: Error | null;
  onRetry?: () => void;
  title?: string;
  description?: string;
}

export default function StatePanel({ mode, error = null, onRetry, title, description }: StatePanelProps) {
  if (mode === 'loading') return <div className="flex min-h-28 items-center justify-center gap-3 text-sm text-secondaryText"><RefreshCw size={16} className="animate-spin" />{title ?? 'Loading from API…'}</div>;
  const Icon = mode === 'error' ? (error && 'status' in error && (error as Error & { status?: number }).status === 0 ? WifiOff : AlertTriangle) : Database;
  const heading = title ?? (mode === 'error' ? errorTitle(error) : mode === 'empty' ? 'No records returned' : 'Data not available');
  return (
    <div className="flex min-h-32 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line px-4 py-6 text-center">
      <Icon size={20} className={mode === 'error' ? 'text-warning' : 'text-mutedText'} />
      <p className="text-sm font-medium text-primaryText">{heading}</p>
      <p className="max-w-lg text-xs leading-5 text-secondaryText">{description ?? (mode === 'error' ? 'The request did not complete. Existing content has been preserved where possible.' : mode === 'empty' ? 'The API returned no records for this view.' : 'The supplied API contract does not expose the fields required for this view.')}</p>
      {mode === 'error' && onRetry && <button className="button-secondary mt-2" type="button" onClick={onRetry}><RefreshCw size={14} /> Retry request</button>}
    </div>
  );
}
