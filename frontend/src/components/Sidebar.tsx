import {
  Activity, BarChart3, BriefcaseBusiness, ChartNoAxesCombined, GitBranch,
  LayoutDashboard, Search, SlidersHorizontal, X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export type PageId = 'dashboard' | 'assets' | 'analysis' | 'calibration' | 'backtest' | 'portfolio' | 'evolution';

export interface NavItem { id: PageId; label: string; icon: LucideIcon; group: 'workspace' | 'models' | 'account'; }
export const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, group: 'workspace' },
  { id: 'assets', label: 'Asset search', icon: Search, group: 'workspace' },
  { id: 'analysis', label: 'Investment analysis', icon: ChartNoAxesCombined, group: 'workspace' },
  { id: 'calibration', label: 'Calibration', icon: SlidersHorizontal, group: 'models' },
  { id: 'backtest', label: 'Backtesting', icon: BarChart3, group: 'models' },
  { id: 'evolution', label: 'Prompt evolution', icon: GitBranch, group: 'models' },
  { id: 'portfolio', label: 'Portfolio', icon: BriefcaseBusiness, group: 'account' },
];

interface SidebarProps { activePage: PageId; onNavigate: (page: PageId) => void; open: boolean; onClose: () => void; }

export default function Sidebar({ activePage, onNavigate, open, onClose }: SidebarProps) {
  const renderGroup = (group: NavItem['group'], title: string) => (
    <div className="mb-6" key={group}>
      <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[.16em] text-mutedText">{title}</p>
      <div className="space-y-1">{NAV_ITEMS.filter((item) => item.group === group).map((item) => {
        const Icon = item.icon;
        return <button key={item.id} onClick={() => { onNavigate(item.id); onClose(); }} className={`nav-item ${activePage === item.id ? 'nav-item-active' : ''}`} type="button" aria-current={activePage === item.id ? 'page' : undefined}>
          <Icon size={17} strokeWidth={1.8} /> <span>{item.label}</span>{activePage === item.id && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-accent" />}
        </button>;
      })}</div>
    </div>
  );

  return <>
    {open && <button className="fixed inset-0 z-40 bg-black/60 lg:hidden" aria-label="Close navigation" type="button" onClick={onClose} />}
    <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
      <div className="flex h-[68px] items-center gap-3 border-b border-line px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-canvas"><Activity size={18} strokeWidth={2.5} /></div>
        <div className="min-w-0 flex-1"><p className="text-sm font-bold tracking-[.08em] text-primaryText">FINTRAC</p><p className="text-[10px] tracking-[.16em] text-mutedText">RESEARCH TERMINAL · V3</p></div>
        <button type="button" className="icon-button lg:hidden" onClick={onClose} aria-label="Close menu"><X size={16} /></button>
      </div>
      <nav className="px-3 py-5">{renderGroup('workspace', 'Workspace')}{renderGroup('models', 'Model intelligence')}{renderGroup('account', 'Account')}</nav>
      <div className="absolute bottom-0 left-0 right-0 border-t border-line p-4">
        <div className="flex items-center gap-2 text-xs text-secondaryText"><span className="h-2 w-2 rounded-full bg-gain" /> API-backed data mode</div>
        <p className="mt-2 text-[10px] text-mutedText">Model values are displayed only when returned by the API.</p>
      </div>
    </aside>
  </>;
}
