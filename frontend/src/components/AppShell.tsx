import type { ReactNode } from 'react';
import { BriefcaseBusiness, LayoutDashboard } from 'lucide-react';
import Sidebar from './Sidebar';
import type { PageId } from './Sidebar';
import TopBar from './TopBar';
import type { UserResponse } from '../api/types';

interface AppShellProps {
  activePage: PageId;
  onNavigate: (page: PageId) => void;
  sidebarOpen: boolean;
  onSidebarClose: () => void;
  onSidebarOpen: () => void;
  user: UserResponse | null;
  darkMode: boolean;
  onToggleTheme: () => void;
  onAuth: () => void;
  onLogout: () => void;
  healthStatus: 'checking' | 'online' | 'offline';
  children: ReactNode;
}

export default function AppShell(props: AppShellProps) {
  return <div className="app-shell">
    <Sidebar activePage={props.activePage} onNavigate={props.onNavigate} open={props.sidebarOpen} onClose={props.onSidebarClose} />
    <div className="app-main">
      <TopBar activePage={props.activePage} user={props.user} darkMode={props.darkMode} onToggleTheme={props.onToggleTheme} onOpenMenu={props.onSidebarOpen} onAuth={props.onAuth} onLogout={props.onLogout} healthStatus={props.healthStatus} />
      <div className="tablet-nav">
        {(['dashboard', 'assets', 'analysis', 'calibration', 'backtest', 'evolution', 'portfolio'] as PageId[]).map((page) => {
          const Icon = page === 'dashboard' ? LayoutDashboard : page === 'portfolio' ? BriefcaseBusiness : undefined;
          const label = page === 'analysis' ? 'Analysis' : page === 'calibration' ? 'Calibration' : page === 'backtest' ? 'Backtesting' : page === 'evolution' ? 'Evolution' : page === 'assets' ? 'Assets' : page[0].toUpperCase() + page.slice(1);
          return <button className={props.activePage === page ? 'tablet-nav-active' : ''} key={page} type="button" onClick={() => props.onNavigate(page)}>{Icon && <Icon size={14} />}{label}</button>;
        })}
      </div>
      <main className="content-area">{props.children}</main>
      <nav className="mobile-nav" aria-label="Mobile navigation">
        <button type="button" onClick={() => props.onNavigate('dashboard')} className={props.activePage === 'dashboard' ? 'mobile-nav-active' : ''}><LayoutDashboard size={18} /><span>Dashboard</span></button>
        <button type="button" onClick={() => props.onNavigate('portfolio')} className={props.activePage === 'portfolio' ? 'mobile-nav-active' : ''}><BriefcaseBusiness size={18} /><span>Portfolio</span></button>
      </nav>
    </div>
  </div>;
}
