import { ChevronDown, ChevronUp } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { JsonRecord } from '../../api/types';
import { humanizeKey, safeText } from '../../lib/format';
import StatusBadge from './StatusBadge';
import StatePanel from './StatePanel';

interface DynamicTableProps {
  rows: JsonRecord[];
  emptyTitle?: string;
  emptyDescription?: string;
  maxColumns?: number;
  onRowClick?: (row: JsonRecord) => void;
}

const PREFERRED_FIELDS = ['ticker', 'symbol', 'name', 'company_name', 'status', 'direction', 'confidence', 'horizon', 'accuracy', 'created_at', 'date'];

export default function DynamicTable({ rows, emptyTitle = 'No records returned', emptyDescription, maxColumns = 7, onRowClick }: DynamicTableProps) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortAscending, setSortAscending] = useState(true);
  const columns = useMemo(() => {
    const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
    keys.sort((a, b) => {
      const ia = PREFERRED_FIELDS.indexOf(a.toLowerCase());
      const ib = PREFERRED_FIELDS.indexOf(b.toLowerCase());
      if (ia >= 0 || ib >= 0) return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
      return a.localeCompare(b);
    });
    return keys.slice(0, maxColumns);
  }, [rows, maxColumns]);
  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;
    return [...rows].sort((a, b) => {
      const av = a[sortKey]; const bv = b[sortKey];
      const cmp = typeof av === 'number' && typeof bv === 'number' ? av - bv : safeText(av).localeCompare(safeText(bv));
      return sortAscending ? cmp : -cmp;
    });
  }, [rows, sortKey, sortAscending]);

  if (!rows.length) return <StatePanel mode="empty" title={emptyTitle} description={emptyDescription} />;
  if (!columns.length) return <StatePanel mode="unavailable" title="Response has no tabular fields" />;

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead><tr>{columns.map((key) => (
          <th key={key} scope="col">
            <button type="button" className="table-sort" onClick={() => { setSortAscending(key === sortKey ? !sortAscending : true); setSortKey(key); }}>
              {humanizeKey(key)} {sortKey === key && (sortAscending ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
            </button>
          </th>
        ))}</tr></thead>
        <tbody>{sortedRows.map((row, index) => (
          <tr key={typeof row.id === 'string' ? row.id : `${index}-${safeText(row.ticker ?? row.symbol)}`} onClick={() => onRowClick?.(row)} className={onRowClick ? 'cursor-pointer hover:bg-raised/70' : ''}>
            {columns.map((key) => {
              const value = row[key];
              const isStatus = /status|state|stage/i.test(key) && typeof value === 'string';
              return <td key={key} title={typeof value === 'string' ? value : undefined}>{isStatus ? <StatusBadge value={value as string} /> : <span className={typeof value === 'number' ? 'font-mono tabular-nums' : ''}>{safeText(value)}</span>}</td>;
            })}
          </tr>
        ))}</tbody>
      </table>
      {rows.some((row) => Object.keys(row).length > maxColumns) && <p className="border-t border-line px-3 py-2 text-xs text-mutedText">Showing {maxColumns} of {columns.length} inferred columns.</p>}
    </div>
  );
}
