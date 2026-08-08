import { createContext, useContext, ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
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
  const queryClient = useQueryClient()

  const { data, isPending, isFetching, refetch } = useQuery<User | null>({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      try {
        const res = await apiClient.get('/auth/me')
        return res.data as User
      } catch (err: any) {
        // 401 = anonymous. Return null so the query is "successful" with no user
        // and TanStack Query stops distinguishing between "not fetched" and
        // "fetched, not authenticated". Any other error rethrows.
        if (err?.response?.status === 401) return null
        throw err
      }
    },
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  // Derive `user` directly from the query result — this avoids the intermediate
  // React render where `isPending=false` (query done) but a separate useState
  // for `user` was still `null` (effect hadn't run yet). That single render is
  // what caused ProtectedRoute to bounce to /login on hard navigations.
  const user: User | null = data ?? null

  // Truly loading = initial fetch OR a manual refetch is running.
  const loading = isPending || isFetching

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
    // Clear the cached query result so subsequent navigation doesn't see the
    // old identity. `user` is derived from this cache, so this is sufficient.
    queryClient.setQueryData(['auth', 'me'], null)
  }

  const devLogin = async () => {
    const res = await apiClient.post('/auth/dev-login')
    if (!res.data || res.data.status !== 'ok') {
      throw new Error('Dev login failed')
    }
    await refetch()
  }

  const initializeAuth = async () => {
    // Kept for backward-compat with AppRoutes; the query runs automatically
    // on mount so this is effectively a manual refresh.
    try {
      await refetch()
    } catch {
      // Not authenticated — the useQuery already handled it.
    }
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
