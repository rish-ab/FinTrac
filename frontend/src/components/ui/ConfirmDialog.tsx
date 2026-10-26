import { AlertTriangle, LoaderCircle, X } from 'lucide-react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  loading?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export default function ConfirmDialog({ open, title, description, confirmLabel = 'Confirm', loading = false, onCancel, onConfirm }: ConfirmDialogProps) {
  if (!open) return null;
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !loading) onCancel(); }}>
    <section className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-warning/30 bg-warning/10 text-warning"><AlertTriangle size={19} /></div>
        <div className="min-w-0 flex-1"><h2 id="confirm-title" className="text-base font-semibold text-primaryText">{title}</h2><p className="mt-2 text-sm leading-6 text-secondaryText">{description}</p></div>
        <button type="button" className="icon-button" onClick={onCancel} disabled={loading} aria-label="Close confirmation"><X size={16} /></button>
      </div>
      <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button type="button" className="button-secondary justify-center" onClick={onCancel} disabled={loading}>Cancel</button>
        <button type="button" className="button-primary justify-center" onClick={onConfirm} disabled={loading}>{loading ? <LoaderCircle size={15} className="animate-spin" /> : null}{loading ? 'Request in progress…' : confirmLabel}</button>
      </div>
    </section>
  </div>;
}
