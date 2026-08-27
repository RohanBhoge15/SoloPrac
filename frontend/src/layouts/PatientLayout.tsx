import { useState } from 'react'
import { Link, useLocation, useNavigate, Outlet } from 'react-router-dom'
import { cn } from '@/utils/helpers'
import { CalendarDays, Home, FileText, Bell, LogOut, Menu, X, Search, User, Loader2 } from 'lucide-react'
import { apiClient } from '@/services/api'

const NAV_ITEMS = [
  { path: '/patient/dashboard', label: 'Dashboard', icon: Home },
  { path: '/patient/search', label: 'Find Doctors', icon: Search },
  { path: '/patient/appointments', label: 'Appointments', icon: CalendarDays },
  { path: '/patient/inbox', label: 'Inbox', icon: Bell },
  { path: '/patient/reports', label: 'Reports', icon: FileText },
  { path: '/patient/profile', label: 'My Profile', icon: User },
]

export function PatientLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)

  // The prior "logout" was `<Link to="/patient/login">` — it navigated to the
  // login page but left the HttpOnly `patient_token` cookie alive on the
  // browser, so hitting Back or typing a patient URL re-authenticated
  // immediately. We POST /public/auth/logout so the backend clears the cookie
  // via Set-Cookie, then navigate.
  const handleLogout = async () => {
    if (loggingOut) return
    setLoggingOut(true)
    try {
      await apiClient.post('/public/auth/logout')
    } catch {
      // Even if the server call fails, we still want to navigate away; the
      // cookie might survive but the user has clearly asked to leave.
    } finally {
      setLoggingOut(false)
      navigate('/patient/login', { replace: true })
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}

      <aside className={cn(
        'fixed left-0 top-0 z-30 h-screen w-64 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 transition-transform duration-300 lg:translate-x-0',
        mobileOpen ? 'translate-x-0' : '-translate-x-full'
      )}>
        <div className="flex h-16 items-center justify-between px-4 border-b border-gray-200 dark:border-gray-700">
          <Link to="/patient/dashboard" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600">
              <span className="text-white font-bold text-sm">SP</span>
            </div>
            <span className="font-semibold text-sm text-gray-900 dark:text-white">Patient Portal</span>
          </Link>
          <button className="lg:hidden p-1" onClick={() => setMobileOpen(false)}>
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = location.pathname === item.path
            return (
              <Link
                key={item.path}
                to={item.path}
                className={cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300' : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800'
                )}
              >
                <item.icon className="h-5 w-5" />
                <span>{item.label}</span>
              </Link>
            )
          })}
        </nav>

        <div className="p-3 border-t border-gray-200 dark:border-gray-700">
          <button
            type="button"
            onClick={handleLogout}
            disabled={loggingOut}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-600 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-60"
          >
            {loggingOut ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <LogOut className="h-4 w-4" />
            )}
            <span>{loggingOut ? 'Logging out…' : 'Logout'}</span>
          </button>
        </div>
      </aside>

      <main className="lg:ml-64 min-h-screen">
        <header className="sticky top-0 z-20 h-16 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm border-b border-gray-200 dark:border-gray-800 lg:hidden">
          <div className="flex h-full items-center px-4">
            <button className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800" onClick={() => setMobileOpen(true)}>
              <Menu className="h-6 w-6" />
            </button>
            <span className="ml-3 font-semibold text-sm text-gray-900 dark:text-white">Patient Portal</span>
          </div>
        </header>
        <div className="p-4 lg:p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
