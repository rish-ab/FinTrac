import { useCallback, useMemo, useState, type FormEvent } from 'react';
import { BriefcaseBusiness, Plus, RefreshCw, ShieldCheck, Trash2, Wallet } from 'lucide-react';
import { ApiError, api } from '../../api/client';
import type { PortfolioCreate, PortfolioResponse, UserResponse, WatchlistCreate, WatchlistResponse } from '../../api/types';
import { safeText } from '../../lib/format';
import { useApiQuery } from '../../hooks/useApiQuery';
import Panel from '../../components/ui/Panel';
import StatePanel from '../../components/ui/StatePanel';
import StatusBadge from '../../components/ui/StatusBadge';
import ConfirmDialog from '../../components/ui/ConfirmDialog';

interface PortfolioPageProps { user: UserResponse | null; onSignIn: () => void; }

export default function PortfolioPage({ user, onSignIn }: PortfolioPageProps) {
  const portfolioLoader = useCallback(() => user ? api.portfolios() : Promise.resolve([] as PortfolioResponse[]), [user]);
  const watchlistLoader = useCallback(() => user ? api.watchlist() : Promise.resolve([] as WatchlistResponse[]), [user]);
  const portfolios = useApiQuery<PortfolioResponse[]>(portfolioLoader, [user]);
  const watchlist = useApiQuery<WatchlistResponse[]>(watchlistLoader, [user]);
  const [showCreate, setShowCreate] = useState(false);
  const [portfolioName, setPortfolioName] = useState('');
  const [baseCurrency, setBaseCurrency] = useState('USD');
  const [objective, setObjective] = useState('');
  const [assetTicker, setAssetTicker] = useState('');
  const [selectedPortfolio, setSelectedPortfolio] = useState('');
  const [operationLoading, setOperationLoading] = useState(false);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [operationSuccess, setOperationSuccess] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ kind: 'portfolio' | 'watchlist'; id: string; label: string } | null>(null);
  const [isDeleteLoading, setIsDeleteLoading] = useState(false);

  const portfolioRows = portfolios.data ?? [];
  const watchlistRows = watchlist.data ?? [];
  const needsLogin = useMemo(() => [portfolios.error, watchlist.error].some((error) => error instanceof ApiError && (error.status === 401 || error.status === 403)), [portfolios.error, watchlist.error]);

  function refresh() { portfolios.refresh(); watchlist.refresh(); }

  async function createPortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setOperationLoading(true); setOperationError(null); setOperationSuccess(null);
    const payload: PortfolioCreate = { name: portfolioName.trim(), base_currency: baseCurrency, objective: objective.trim() || null };
    try {
      await api.createPortfolio(payload);
      setPortfolioName(''); setObjective(''); setShowCreate(false); setOperationSuccess('Portfolio created.'); portfolios.refresh();
    } catch (reason) { setOperationError(reason instanceof Error ? reason.message : 'Could not create portfolio.'); }
    finally { setOperationLoading(false); }
  }

  async function addAsset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setOperationLoading(true); setOperationError(null); setOperationSuccess(null);
    const payload: WatchlistCreate = { ticker: assetTicker.trim().toUpperCase(), portfolio_id: selectedPortfolio || null };
    try {
      await api.addWatchlistItem(payload);
      setAssetTicker(''); setOperationSuccess('Asset added to watchlist.'); watchlist.refresh();
    } catch (reason) { setOperationError(reason instanceof Error ? reason.message : 'Could not update watchlist.'); }
    finally { setOperationLoading(false); }
  }

  async function deleteConfirmed() {
    if (!deleteTarget) return;
    setIsDeleteLoading(true); setOperationError(null); setOperationSuccess(null);
    try {
      if (deleteTarget.kind === 'portfolio') await api.deletePortfolio(deleteTarget.id);
      else await api.removeWatchlistItem(deleteTarget.id);
      setOperationSuccess(deleteTarget.kind === 'portfolio' ? 'Portfolio deleted.' : 'Watchlist item removed.');
      setDeleteTarget(null); refresh();
    } catch (reason) { setDeleteTarget(null); setOperationError(reason instanceof Error ? reason.message : 'Delete operation failed.'); }
    finally { setIsDeleteLoading(false); }
  }

  return <div className="page-stack">
    <div className="page-intro"><div><p className="eyebrow">PORTFOLIO MANAGEMENT</p><h2 className="page-title">Portfolio</h2><p className="page-description">Manage portfolio metadata and watchlist entries. Position valuation is not fabricated when holdings data is unavailable.</p></div><button type="button" className="button-secondary" onClick={refresh} disabled={!user}><RefreshCw size={14} /> Refresh</button></div>

    {!user && <div className="rounded-xl border border-warning/30 bg-warning/5 p-5"><div className="flex items-start gap-3"><ShieldCheck size={21} className="mt-0.5 text-warning" /><div className="min-w-0 flex-1"><h3 className="text-base font-semibold text-primaryText">Sign in to access your portfolios</h3><p className="mt-1 text-sm leading-6 text-secondaryText">The OpenAPI contract requires bearer authentication for portfolio and watchlist endpoints. Public dashboard and asset-search views remain available without a session.</p><button type="button" className="button-primary mt-4" onClick={onSignIn}>Sign in</button></div></div></div>}

    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div className="metric-card"><p className="metric-label">Portfolio value</p><p className="mt-3 text-2xl font-semibold text-primaryText">Unavailable</p><p className="mt-2 text-xs leading-5 text-secondaryText">Holdings and current position prices are not exposed by the documented API.</p></div>
      <div className="metric-card"><p className="metric-label">Unrealized P&amp;L</p><p className="mt-3 text-2xl font-semibold text-primaryText">Unavailable</p><p className="mt-2 text-xs leading-5 text-secondaryText">Requires position quantities and cost basis.</p></div>
      <div className="metric-card"><p className="metric-label">Allocation</p><p className="mt-3 text-2xl font-semibold text-primaryText">Unavailable</p><p className="mt-2 text-xs leading-5 text-secondaryText">Watchlist entries are not treated as holdings.</p></div>
      <div className="metric-card"><p className="metric-label">Managed portfolios</p><p className="mt-3 font-mono text-2xl font-semibold text-primaryText">{user && portfolios.data ? portfolios.data.length : '—'}</p><p className="mt-2 text-xs leading-5 text-secondaryText">Count from the portfolio-list response when available.</p></div>
    </div>

    {operationError && <div className="rounded-lg border border-loss/30 bg-loss/10 p-3 text-sm text-loss" role="alert">{operationError}</div>}
    {operationSuccess && <div className="rounded-lg border border-gain/30 bg-gain/10 p-3 text-sm text-gain" role="status">{operationSuccess}</div>}
    {needsLogin && <StatePanel mode="error" error={portfolios.error ?? watchlist.error} title="Your session may have expired" description="Sign in again to reload protected portfolio data." />}

    <Panel title="Your portfolios" subtitle="GET /api/v1/portfolios/ · Create or delete portfolio metadata" action={user && <button type="button" className="button-primary" onClick={() => setShowCreate((value) => !value)}><Plus size={14} /> New portfolio</button>} onRefresh={portfolios.refresh} loading={portfolios.loading}>
      {showCreate && <form onSubmit={createPortfolio} className="mb-4 grid grid-cols-1 gap-3 rounded-lg border border-line bg-canvas/40 p-4 md:grid-cols-2">
        <label className="form-label">Portfolio name<input className="input-control mt-2" value={portfolioName} onChange={(event) => setPortfolioName(event.target.value)} required maxLength={120} /></label>
        <label className="form-label">Base currency<input className="input-control mt-2 uppercase" value={baseCurrency} onChange={(event) => setBaseCurrency(event.target.value.toUpperCase())} required maxLength={10} /></label>
        <label className="form-label md:col-span-2">Objective (optional)<textarea className="input-control mt-2 min-h-16" value={objective} onChange={(event) => setObjective(event.target.value)} /></label>
        <div className="flex gap-2 md:col-span-2"><button type="submit" className="button-primary" disabled={operationLoading || !portfolioName.trim()}>{operationLoading ? 'Creating…' : 'Create portfolio'}</button><button type="button" className="button-secondary" onClick={() => setShowCreate(false)}>Cancel</button></div>
      </form>}
      {!user ? <StatePanel mode="unavailable" title="Sign in required" description="Portfolio data will appear after authentication." /> : portfolios.loading && !portfolios.data ? <StatePanel mode="loading" title="Loading portfolios" /> : portfolios.error && !portfolios.data ? <StatePanel mode="error" error={portfolios.error} onRetry={portfolios.refresh} /> : portfolioRows.length ? <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">{portfolioRows.map((portfolio) => <div className="rounded-lg border border-line bg-canvas/40 p-4" key={portfolio.id}><div className="flex items-start justify-between gap-3"><div className="flex min-w-0 items-start gap-3"><div className="rounded-lg border border-line bg-raised p-2 text-secondaryText"><BriefcaseBusiness size={17} /></div><div className="min-w-0"><h3 className="break-words text-sm font-semibold text-primaryText">{portfolio.name}</h3><p className="mt-1 font-mono text-xs text-secondaryText">{portfolio.base_currency}</p></div></div><button type="button" className="icon-button danger-hover" aria-label={`Delete ${portfolio.name}`} title="Delete portfolio" onClick={() => setDeleteTarget({ kind: 'portfolio', id: portfolio.id, label: portfolio.name })}><Trash2 size={14} /></button></div>{portfolio.objective && <p className="mt-3 line-clamp-3 text-xs leading-5 text-secondaryText">{portfolio.objective}</p>}<p className="mt-3 text-[10px] text-mutedText">ID: {portfolio.id}</p></div>)}</div> : <StatePanel mode="empty" title="No portfolios yet" description="Create a portfolio to organize watchlist assets. The API does not currently expose positions or trades." />}
    </Panel>

    <Panel title="Watchlist" subtitle="GET /api/v1/portfolios/watchlist · Price and sentiment triggers are optional" onRefresh={watchlist.refresh} loading={watchlist.loading}>
      {user && <form className="mb-4 flex flex-col gap-3 rounded-lg border border-line bg-canvas/40 p-3 sm:flex-row" onSubmit={addAsset}><label className="form-label flex-1">Ticker<input className="input-control mt-2 font-mono uppercase" value={assetTicker} onChange={(event) => setAssetTicker(event.target.value.toUpperCase())} required maxLength={20} placeholder="Add ticker" /></label><label className="form-label flex-1">Portfolio (optional)<select className="input-control mt-2" value={selectedPortfolio} onChange={(event) => setSelectedPortfolio(event.target.value)}><option value="">No portfolio association</option>{portfolioRows.map((portfolio) => <option value={portfolio.id} key={portfolio.id}>{portfolio.name}</option>)}</select></label><button className="button-primary self-end sm:mb-0.5" type="submit" disabled={operationLoading}><Plus size={14} /> Add asset</button></form>}
      {!user ? <StatePanel mode="unavailable" title="Sign in required" description="The watchlist is user-specific and requires bearer authentication." /> : watchlist.loading && !watchlist.data ? <StatePanel mode="loading" title="Loading watchlist" /> : watchlist.error && !watchlist.data ? <StatePanel mode="error" error={watchlist.error} onRetry={watchlist.refresh} /> : watchlistRows.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Ticker</th><th>Association</th><th>Price triggers</th><th>Sentiment triggers</th><th /></tr></thead><tbody>{watchlistRows.map((item) => <tr key={item.id}><td><span className="font-mono font-semibold text-primaryText">{item.ticker}</span></td><td>{item.portfolio_id ? portfolioRows.find((p) => p.id === item.portfolio_id)?.name ?? item.portfolio_id : 'Unassigned'}</td><td><div className="flex gap-2 text-xs"><span>High {safeText(item.price_trigger_high)}</span><span>Low {safeText(item.price_trigger_low)}</span></div></td><td><div className="flex gap-2 text-xs"><span>High {safeText(item.sentiment_trigger_high)}</span><span>Low {safeText(item.sentiment_trigger_low)}</span></div></td><td><button type="button" className="icon-button danger-hover" aria-label={`Remove ${item.ticker}`} onClick={() => setDeleteTarget({ kind: 'watchlist', id: item.id, label: item.ticker })}><Trash2 size={14} /></button></td></tr>)}</tbody></table></div> : <StatePanel mode="empty" title="Watchlist is empty" description="Add assets to track them or configure optional trigger thresholds." />}
    </Panel>

    <Panel title="Holdings, P&L and allocation" subtitle="These features require position-level backend data"><div className="flex items-start gap-3 rounded-lg border border-dashed border-line p-4"><Wallet size={19} className="mt-0.5 text-mutedText" /><div><p className="text-sm font-medium text-primaryText">Portfolio valuation is not available from the supplied contract</p><p className="mt-1 text-xs leading-5 text-secondaryText">The documented endpoints manage portfolio metadata and watchlist thresholds, but do not expose position quantities, trades, cost basis, live valuations, or realized/unrealized P&amp;L. These sections remain unavailable rather than treating watchlist items as holdings.</p><p className="mt-3 text-xs text-secondaryText">Snapshot endpoint available for individual assets: <StatusBadge value="GET /api/v1/analysis/snapshot" /></p></div></div></Panel>

    <ConfirmDialog open={Boolean(deleteTarget)} title={deleteTarget?.kind === 'portfolio' ? 'Delete portfolio?' : 'Remove watchlist item?'} description={deleteTarget?.kind === 'portfolio' ? `This will send DELETE /api/v1/portfolios/${deleteTarget.id}. The endpoint deletes portfolio metadata; confirm only if you intend to perform this action.` : `This will remove ${deleteTarget?.label ?? 'the selected item'} from your watchlist using the documented DELETE endpoint.`} confirmLabel={deleteTarget?.kind === 'portfolio' ? 'Delete portfolio' : 'Remove item'} loading={isDeleteLoading} onCancel={() => setDeleteTarget(null)} onConfirm={() => { void deleteConfirmed(); }} />
  </div>;
}
