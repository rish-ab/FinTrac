import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Navbar() {
  const { user, logoutUser } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logoutUser()
    navigate('/login')
  }

  return (
    <nav className="navbar navbar-expand sticky-top">
      <div className="container-fluid">
        <span className="navbar-brand">FINTRAC</span>

        <div className="d-flex align-items-center gap-1">
          <NavLink to="/dashboard" className={({ isActive }) =>
            `nav-link ${isActive ? 'active' : ''}`
          }>
            Dashboard
          </NavLink>
          <NavLink to="/portfolios" className={({ isActive }) =>
            `nav-link ${isActive ? 'active' : ''}`
          }>
            Portfolios
          </NavLink>
          <NavLink to="/watchlist" className={({ isActive }) =>
            `nav-link ${isActive ? 'active' : ''}`
          }>
            Watchlist
          </NavLink>
        </div>

        <div className="d-flex align-items-center gap-3 ms-auto">
          <span style={{
            fontFamily: 'var(--ft-mono)',
            fontSize: '11px',
            color: 'var(--ft-text-muted)',
          }}>
            {user?.email}
          </span>
          <button
            className="btn btn-outline-secondary btn-sm"
            onClick={handleLogout}
          >
            Logout
          </button>
        </div>
      </div>
    </nav>
  )
}
