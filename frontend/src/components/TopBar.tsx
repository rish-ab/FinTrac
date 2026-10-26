import { Menu, Moon, Sun, UserRound, LogOut, ShieldCheck, CircleHelp } from 'lucide-react';
import type { UserResponse } from '../api/types';
import type { PageId } from './Sidebar';
import { NAV_ITEMS } from './Sidebar';

interface TopBarProps {
  activePage: PageId;
  user: UserResponse | null;
  darkMode: boolean;
  onToggleTheme: () => void;
  onOpenMenu: () => void;
  onAuth: () => void;
  onLogout: () => void;
  healthStatus: 'checking' | 'online' | 'offline';
}

export default function TopBar({ activePage, user, darkMode, onToggleTheme, onOpenMenu, onAuth, onLogout, healthStatus }: TopBarProps) {
  const activeItem = NAV_ITEMS.find((item) => item.id === activePage);
  return <header className="topbar">
    <div className="flex min-w-0 items-center gap-3">
      <button type="button" className="icon-button lg:hidden" onClick={onOpenMenu} aria-label="Open navigation"><Menu size={18} /></button>
      <div className="min-w-0"><p className="text-[10px] uppercase tracking-[.16em] text-mutedText">FinTrac / Workspace</p><h1 className="truncate text-sm font-semibold text-primaryText sm:text-base">{activeItem?.label ?? 'Dashboard'}</h1></div>
    </div>
    <div className="flex items-center gap-2 sm:gap-3">
      <div className="hidden items-center gap-2 text-xs text-secondaryText md:flex"><span className={`h-1.5 w-1.5 rounded-full ${healthStatus === 'online' ? 'bg-gain' : healthStatus === 'offline' ? 'bg-loss' : 'bg-mutedText'}`} /> {healthStatus === 'online' ? 'API online' : healthStatus === 'offline' ? 'API unreachable' : 'Checking API'}</div>
      <span className="hidden h-5 w-px bg-line sm:block" />
      <button type="button" className="icon-button" aria-label={`Switch to ${darkMode ? 'light' : 'dark'} theme`} title={`Switch to ${darkMode ? 'light' : 'dark'} theme`} onClick={onToggleTheme}>{darkMode ? <Sun size={16} /> : <Moon size={16} />}</button>
      <button type="button" className="button-secondary hidden sm:inline-flex" onClick={() => window.open('https://fastapi.tiangolo.com/', '_blank', 'noopener,noreferrer')}><CircleHelp size={14} /> API help</button>
      {user ? <div className="flex items-center gap-2">
        <div className="hidden text-right sm:block"><p className="max-w-36 truncate text-xs font-medium text-primaryText">{user.email}</p><p className="flex items-center justify-end gap-1 text-[10px] text-gain"><ShieldCheck size={10} /> Signed in</p></div>
        <button type="button" className="icon-button" title="Sign out" aria-label="Sign out" onClick={onLogout}><LogOut size={16} /></button>
      </div> : <button type="button" className="button-primary" onClick={onAuth}><UserRound size={14} /><span>Sign in</span></button>}
    </div>
  </header>;
}
