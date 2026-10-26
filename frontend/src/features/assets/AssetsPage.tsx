import { useEffect, useMemo, useState } from 'react';
import { ArrowUpRight, Search, SearchX } from 'lucide-react';
import { api } from '../../api/client';
import type { AssetSearchResult, JsonRecord } from '../../api/types';
import { humanizeKey, isRecord, safeText } from '../../lib/format';
import { useApiQuery } from '../../hooks/useApiQuery';
import Panel from '../../components/ui/Panel';
import StatePanel from '../../components/ui/StatePanel';

interface AssetsPageProps { onSelectAsset: (ticker: string) => void; }

function assetTicker(record: JsonRecord): string | undefined {
  const value = [record.ticker, record.symbol, record.code].find((item) => typeof item === 'string' && item.trim());
  return typeof value === 'string' ? value : undefined;
}
function assetName(record: JsonRecord): string {
  const value = [record.company_name, record.name, record.description].find((item) => typeof item === 'string' && item.trim());
  return typeof value === 'string' ? value : 'Name not provided by API';
}
function assetClass(record: JsonRecord): string {
  const value = [record.asset_class, record.class, record.type, record.category].find((item) => typeof item === 'string' && item.trim());
  return typeof value === 'string' ? value : 'Asset class not specified';
}

export default function AssetsPage({ onSelectAsset }: AssetsPageProps) {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [resultData, setResultData] = useState<AssetSearchResult[] | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<Error | null>(null);
  const [searchRevision, setSearchRevision] = useState(0);
  const registryLoader = () => api.assetList();
  const registry = useApiQuery(registryLoader);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedQuery(query.trim()), 300);
    return () => window.clearTimeout(timeout);
  }, [query]);

  useEffect(() => {
    let active = true;
    if (!debouncedQuery) {
      setResultData(null); setSearchLoading(false); setSearchError(null);
      return () => { active = false; };
    }
    setSearchLoading(true); setSearchError(null);
    api.searchAssets(debouncedQuery, 15).then((results) => { if (active) setResultData(results); }).catch((reason: unknown) => { if (active) setSearchError(reason instanceof Error ? reason : new Error('Search failed')); }).finally(() => { if (active) setSearchLoading(false); });
    return () => { active = false; };
  }, [debouncedQuery, searchRevision]);

  const groups = useMemo<Array<{ group: string; items: unknown[] }>>(() => {
    if (!isRecord(registry.data)) return [];
    return Object.entries(registry.data).map(([group, items]) => ({ group, items: Array.isArray(items) ? items : [] })).filter((entry) => entry.items.length > 0);
  }, [registry.data]);

  const pickResult = (record: JsonRecord) => {
    const ticker = assetTicker(record);
    if (ticker) onSelectAsset(ticker);
  };

  return <div className="page-stack">
    <div className="page-intro"><div><p className="eyebrow">MARKET UNIVERSE</p><h2 className="page-title">Asset selector</h2><p className="page-description">Search the curated registry and broader ticker universe using the live API.</p></div></div>
    <Panel title="Search assets" subtitle="Ticker or company name · requests are debounced">
      <div className="relative"><Search size={17} className="absolute left-3 top-1/2 -translate-y-1/2 text-mutedText" /><input className="input-control pl-10" placeholder="Search e.g. a ticker or company name" value={query} maxLength={40} onChange={(event) => setQuery(event.target.value)} aria-label="Search by ticker or company name" /><span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-mutedText">max 40 chars</span></div>
      <p className="mt-2 text-xs text-secondaryText">Search uses <code className="text-primaryText">GET /api/v1/assets/search</code>. No client-side symbol list is substituted for API results.</p>
      <div className="mt-4">
        {searchLoading && <StatePanel mode="loading" title={`Searching ${debouncedQuery}…`} />}
        {!searchLoading && searchError && <StatePanel mode="error" error={searchError} onRetry={() => setSearchRevision((value) => value + 1)} />}
        {!searchLoading && !searchError && debouncedQuery && resultData && resultData.length === 0 && <StatePanel mode="empty" title="No matching assets" description="The API returned zero results for this query. Try a ticker or a different company-name spelling." />}
        {!searchLoading && !searchError && resultData && resultData.length > 0 && <div className="space-y-2">{resultData.map((row, index) => <button key={`${assetTicker(row) ?? 'asset'}-${index}`} type="button" className="asset-result" onClick={() => pickResult(row)}>
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-line bg-raised text-secondaryText"><Search size={15} /></span>
          <span className="min-w-0 flex-1"><span className="flex flex-wrap items-center gap-2"><strong className="font-mono text-sm text-primaryText">{assetTicker(row) ?? 'Ticker not supplied'}</strong><span className="text-[10px] text-mutedText">{assetClass(row)}</span></span><span className="mt-1 block truncate text-xs text-secondaryText">{assetName(row)}</span></span>
          <ArrowUpRight size={15} className="shrink-0 text-mutedText" />
        </button>)}</div>}
        {!searchLoading && !searchError && !debouncedQuery && <div className="flex items-start gap-3 rounded-lg border border-dashed border-line px-4 py-5"><SearchX size={18} className="mt-0.5 text-mutedText" /><div><p className="text-sm font-medium text-primaryText">Start typing to search</p><p className="mt-1 text-xs leading-5 text-secondaryText">The endpoint accepts a non-empty query and returns the matching records. Browse-by-class data is shown below when the registry loads.</p></div></div>}
      </div>
    </Panel>

    <Panel title="Browse by asset class" subtitle="Curated registry returned by the API" onRefresh={registry.refresh} loading={registry.loading}>
      {registry.loading && !registry.data ? <StatePanel mode="loading" title="Loading asset registry" /> : registry.error && !registry.data ? <StatePanel mode="error" error={registry.error} onRetry={registry.refresh} /> : groups.length ? <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">{groups.map(({ group, items }) => <div className="rounded-lg border border-line bg-canvas/40 p-3" key={group}><div className="mb-3 flex items-center justify-between gap-2"><h3 className="text-sm font-semibold text-primaryText">{humanizeKey(group)}</h3><span className="text-xs text-mutedText">{items.length} listed</span></div><div className="flex flex-wrap gap-2">{items.slice(0, 24).map((item, index) => {
        const record = isRecord(item) ? item : { ticker: String(item) };
        const ticker = assetTicker(record) ?? (typeof item === 'string' ? item : undefined);
        return ticker ? <button key={`${ticker}-${index}`} type="button" className="ticker-chip" onClick={() => onSelectAsset(ticker)} title={assetName(record)}>{ticker}</button> : <span key={index} className="ticker-chip-static">{safeText(item)}</span>;
      })}</div>{items.length > 24 && <p className="mt-3 text-[11px] text-mutedText">Showing first 24 entries; use search for additional assets.</p>}</div>)}</div> : <StatePanel mode={registry.data ? 'empty' : 'unavailable'} title="Registry groups unavailable" description="The response did not contain grouped registry values in a recognizable shape." />}
    </Panel>
  </div>;
}
