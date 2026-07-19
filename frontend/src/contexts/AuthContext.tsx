import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'

interface User {
  id: string
  email: string
  name: string
  speciality: string
  clinic_name?: string
  settings?: Record<string, any>
}

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (accessToken: string, refreshToken: string) => void
  googleLogin: () => void
  logout: () => void
  initializeAuth: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const { data: userData, refetch } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      const res = await fetch('/api/v1/auth/me')
      if (!res.ok) throw new Error('Not authenticated')
      return res.json()
    },
    enabled: !!localStorage.getItem('access_token'),
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  useEffect(() => {
    if (userData) {
      setUser(userData)
    }
    setLoading(false)
  }, [userData])

  const login = (accessToken: string, refreshToken: string) => {
    localStorage.setItem('access_token', accessToken)
    localStorage.setItem('refresh_token', refreshToken)
    refetch()
  }

  const logout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    setUser(null)
  }

  const googleLogin = () => {
    window.location.href = '/api/v1/auth/login/google'
  }

  const initializeAuth = async () => {
    if (localStorage.getItem('access_token')) {
      try {
        await refetch()
      } catch {
        logout()
      }
    }
    setLoading(false)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, googleLogin, logout, initializeAuth }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}