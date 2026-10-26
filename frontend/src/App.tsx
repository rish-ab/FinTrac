import { useCallback, useEffect, useState } from 'react';
import AppShell from './components/AppShell';
import type { PageId } from './components/Sidebar';
import AuthModal from './components/AuthModal';
import DashboardPage from './features/dashboard/DashboardPage';
import AssetsPage from './features/assets/AssetsPage';
import AnalysisPage from './features/analysis/AnalysisPage';
import CalibrationPage from './features/calibration/CalibrationPage';
import BacktestingPage from './features/backtest/BacktestingPage';
import PortfolioPage from './features/portfolio/PortfolioPage';
import EvolutionPage from './features/evolution/EvolutionPage';
import { api, ApiError } from './api/client';
import { clearAccessToken, getAccessToken, getStoredUser } from './api/token-store';
import type { UserResponse } from './api/types';

export default function App() {
  const [activePage, setActivePage] = useState<PageId>('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [user, setUser] = useState<UserResponse | null>(() => getStoredUser<UserResponse>());
  const [darkMode, setDarkMode] = useState(true);
  const [selectedTicker, setSelectedTicker] = useState<string | undefined>();
  const [healthStatus, setHealthStatus] = useState<'checking' | 'online' | 'offline'>('checking');

  const onNavigate = useCallback((page: PageId) => {
    const mobileViewport = window.matchMedia('(max-width: 767px)').matches;
    if (mobileViewport && page !== 'dashboard' && page !== 'portfolio') {
      setActivePage('dashboard');
    } else {
      setActivePage(page);
    }
    setSidebarOpen(false);
  }, []);
  const clearSelectedTicker = useCallback(() => setSelectedTicker(undefined), []);
  const openAnalysis = useCallback((ticker?: string) => {
    if (window.matchMedia('(max-width: 767px)').matches) {
      setActivePage('dashboard');
      return;
    }
    setSelectedTicker(ticker);
    setActivePage('analysis');
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
    document.documentElement.classList.toggle('light', !darkMode);
  }, [darkMode]);

  useEffect(() => {
    let active = true;
    api.health().then(() => { if (active) setHealthStatus('online'); }).catch(() => { if (active) setHealthStatus('offline'); });
    const onNavigateEvent = (event: Event) => {
      const detail = (event as CustomEvent<unknown>).detail;
      if (typeof detail === 'string' && ['dashboard', 'assets', 'analysis', 'calibration', 'backtest', 'portfolio', 'evolution'].includes(detail)) onNavigate(detail as PageId);
    };
    window.addEventListener('fintrac:navigate', onNavigateEvent);
    return () => { active = false; window.removeEventListener('fintrac:navigate', onNavigateEvent); };
  }, [onNavigate]);

  useEffect(() => {
    if (!getAccessToken()) return;
    let active = true;
    api.me().then((currentUser) => {
      if (!active) return;
      setUser(currentUser);
    }).catch((reason: unknown) => {
      if (!active) return;
      if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
        clearAccessToken(); setUser(null);
      }
    });
    return () => { active = false; };
  }, []);

  function logout() {
    clearAccessToken();
    setUser(null);
    setActivePage('dashboard');
  }

  return <>
    <AppShell activePage={activePage} onNavigate={onNavigate} sidebarOpen={sidebarOpen} onSidebarClose={() => setSidebarOpen(false)} onSidebarOpen={() => setSidebarOpen(true)} user={user} darkMode={darkMode} onToggleTheme={() => setDarkMode((value) => !value)} onAuth={() => setAuthOpen(true)} onLogout={logout} healthStatus={healthStatus}>
      {activePage === 'dashboard' && <DashboardPage onOpenAnalysis={openAnalysis} />}
      {activePage === 'assets' && <AssetsPage onSelectAsset={openAnalysis} />}
      {activePage === 'analysis' && <AnalysisPage selectedTicker={selectedTicker} onTickerConsumed={clearSelectedTicker} />}
      {activePage === 'calibration' && <CalibrationPage />}
      {activePage === 'backtest' && <BacktestingPage />}
      {activePage === 'portfolio' && <PortfolioPage user={user} onSignIn={() => setAuthOpen(true)} />}
      {activePage === 'evolution' && <EvolutionPage />}
    </AppShell>
    {authOpen && <AuthModal onClose={() => setAuthOpen(false)} onAuthenticated={(nextUser) => setUser(nextUser)} />}
  </>;
}
