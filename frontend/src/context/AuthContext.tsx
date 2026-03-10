import { createContext, useContext, useState, ReactNode } from 'react'

interface User { id: string; email: string }

interface AuthContextType {
  user: User | null
  token: string | null
  loginUser: (token: string, user: User) => void
  logoutUser: () => void
  isAuthenticated: boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem('ft_token')
  )
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem('ft_user')
    return raw ? JSON.parse(raw) : null
  })

  const loginUser = (newToken: string, newUser: User) => {
    localStorage.setItem('ft_token', newToken)
    localStorage.setItem('ft_user', JSON.stringify(newUser))
    setToken(newToken)
    setUser(newUser)
  }

  const logoutUser = () => {
    localStorage.removeItem('ft_token')
    localStorage.removeItem('ft_user')
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider
      value={{ user, token, loginUser, logoutUser, isAuthenticated: !!token }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
