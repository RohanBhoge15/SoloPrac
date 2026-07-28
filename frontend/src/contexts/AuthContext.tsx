import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/services/api'

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
  login: (email: string, password: string) => Promise<void>
  devLogin: () => Promise<void>
  logout: () => Promise<void>
  initializeAuth: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const { data: userData, refetch } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      const res = await apiClient.get('/auth/me')
      return res.data
    },
    // enabled when we have cookies (no localStorage check needed)
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  useEffect(() => {
    if (userData) {
      setUser(userData)
    }
    setLoading(false)
  }, [userData])

  const login = async (email: string, password: string) => {
    const res = await apiClient.post('/auth/login', { email, password })
    if (!res.data || res.data.status !== 'ok') {
      throw new Error('Login failed')
    }
    // No localStorage - cookies are set by backend
    await refetch()
  }

  const logout = async () => {
    try {
      await apiClient.post('/auth/logout')
    } catch {
      // Ignore errors
    }
    // No localStorage to clear - cookies are cleared by backend
    setUser(null)
  }

  const devLogin = async () => {
    const res = await apiClient.post('/auth/dev-login')
    if (!res.data || res.data.status !== 'ok') {
      throw new Error('Dev login failed')
    }
    await refetch()
  }

  const initializeAuth = async () => {
    try {
      await refetch()
    } catch {
      // Not authenticated
    }
    setLoading(false)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, devLogin, logout, initializeAuth }}>
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
