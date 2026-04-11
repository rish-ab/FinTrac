import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Navbar from './components/Navbar'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import DashboardPage from './pages/DashboardPage'
import PortfolioPage from './pages/PortfolioPage'
import WatchlistPage from './pages/WatchlistPage'
import CalibrationDashboard from './pages/CalibrationDashboard'
import DashboardWithAssets from './pages/DashboardWithAssets'

function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Navbar />
      <main style={{ minHeight: 'calc(100vh - 52px)' }}>
        {children}
      </main>
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login"    element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/dashboard" element={
            <ProtectedRoute>
              <AppLayout><DashboardWithAssets /></AppLayout>
            </ProtectedRoute>
          } />
          <Route path="/calibration" element={
            <ProtectedRoute>
              <AppLayout><CalibrationDashboard /></AppLayout>
            </ProtectedRoute>
          } />
          <Route path="/portfolios" element={
            <ProtectedRoute>
              <AppLayout><PortfolioPage /></AppLayout>
            </ProtectedRoute>
          } />
          <Route path="/watchlist" element={
            <ProtectedRoute>
              <AppLayout><WatchlistPage /></AppLayout>
            </ProtectedRoute>
          } />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
