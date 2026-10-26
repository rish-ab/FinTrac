import type { ReactNode } from 'react';
import { RefreshCw } from 'lucide-react';

interface PanelProps {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  onRefresh?: () => void;
  loading?: boolean;
  children: ReactNode;
  className?: string;
}

export default function Panel({ title, subtitle, action, onRefresh, loading, children, className = '' }: PanelProps) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div className="min-w-0">
          <h2 className="section-title">{title}</h2>
          {subtitle && <p className="mt-1 text-xs text-secondaryText">{subtitle}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {action}
          {onRefresh && (
            <button className="icon-button" type="button" aria-label={`Refresh ${title}`} onClick={onRefresh} disabled={loading}>
              <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
            </button>
          )}
        </div>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}
