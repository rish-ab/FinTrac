import type { JsonRecord } from '../api/types';

export function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function asRecords(value: unknown): JsonRecord[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord);
}

export function humanizeKey(key: string): string {
  return key.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/^./, (c) => c.toUpperCase());
}

export function safeText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return Number.isFinite(value) ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(value) : '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return value.map(safeText).join(', ');
  if (isRecord(value)) return Object.keys(value).length ? `${Object.keys(value).length} fields` : '—';
  return String(value);
}

export function formatCurrency(value: unknown, currency = 'USD'): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 2 }).format(value);
  } catch {
    return `${currency} ${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)}`;
  }
}

export function formatDate(value: unknown): string {
  if (typeof value !== 'string' || !value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function formatPercent(value: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)}%`;
}

export function firstString(record: JsonRecord, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return undefined;
}

export function firstNumber(record: JsonRecord, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return undefined;
}

export function extractRows(value: unknown): JsonRecord[] {
  if (Array.isArray(value)) return asRecords(value);
  if (!isRecord(value)) return [];
  for (const candidate of Object.values(value)) {
    if (Array.isArray(candidate) && candidate.length > 0 && candidate.every(isRecord)) return candidate;
  }
  return [];
}
