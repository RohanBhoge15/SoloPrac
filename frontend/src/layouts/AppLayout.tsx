import { useState } from 'react'
import { Link, useLocation, Outlet } from 'react-router-dom'
import { cn } from '@/utils/helpers'
import { Button } from '@/components/ui/Button'
import { UserMenu } from '@/components/layout/UserMenu'
import { PatientSearch } from '@/components/PatientSearch'
import { CommandPalette, useCommandPalette } from '@/components/CommandPalette'
import { useAuth } from '@/contexts/AuthContext'
import {
  LayoutDashboard,
  Calendar,
  FileText,
  Settings,
  MessageSquare,
  Mic,
  Bell,
  Menu,
  Plus,
} from 'lucide-react'

const NAV_ITEMS = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/chat', label: 'AI Assistant', icon: MessageSquare },
  { path: '/calendar', label: 'Calendar', icon: Calendar },
  { path: '/scratchpad', label: 'Scratchpad', icon: FileText },
  { path: '/settings', label: 'Settings', icon: Settings },
]

export function AppLayout() {
  const location = useLocation()
  const { user, logout } = useAuth()
  const [sidebarOpen] = useState(true)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const { isOpen: cmdPaletteOpen, openPalette, closePalette } = useCommandPalette()

  const handleLogout = () => {
    logout()
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      {/* Mobile menu overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed left-0 top-0 z-30 h-screen bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 transition-all duration-300 lg:translate-x-0',
          sidebarOpen ? 'w-64' : 'w-20',
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        )}
      >
        {/* Logo / Brand */}
        <div className="flex h-16 items-center justify-between px-4 border-b border-gray-200 dark:border-gray-700">
          <Link to="/dashboard" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600">
              <span className="text-white font-bold text-lg">SP</span>
            </div>
            {sidebarOpen && (
              <span className="font-semibold text-lg text-gray-900 dark:text-white">
                SoloPrac AI
              </span>
            )}
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const isActive = location.pathname === item.path
            return (
              <Link
                key={item.path}
                to={item.path}
                className={cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                    : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800',
                  sidebarOpen ? 'justify-start' : 'justify-center'
                )}
                title={sidebarOpen ? undefined : item.label}
              >
                <item.icon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
                {sidebarOpen && <span>{item.label}</span>}
              </Link>
            )
          })}

          {/* Quick Actions Section */}
          {sidebarOpen && (
            <div className="pt-4 mt-4 border-t border-gray-200 dark:border-gray-700">
              <h3 className="px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Quick Actions
              </h3>
              <div className="mt-2 space-y-1">
                <Button
                  variant="ghost"
                  className="w-full justify-start gap-2"
                  size="sm"
                  onClick={() => {}}
                >
                  <Plus className="h-4 w-4" />
                  <span>New Patient</span>
                </Button>
                <Button
                  variant="ghost"
                  className="w-full justify-start gap-2"
                  size="sm"
                  onClick={() => {}}
                >
                  <FileText className="h-4 w-4" />
                  <span>Upload Document</span>
                </Button>
                <Button
                  variant="ghost"
                  className="w-full justify-start gap-2"
                  size="sm"
                  onClick={() => {}}
                >
                  <Calendar className="h-4 w-4" />
                  <span>Today's Calendar</span>
                </Button>
                <Button
                  variant="ghost"
                  className="w-full justify-start gap-2"
                  size="sm"
                  onClick={() => {}}
                >
                  <Bell className="h-4 w-4" />
                  <span>Weekly Reports</span>
                </Button>
              </div>
            </div>
          )}
        </nav>

        {/* Bottom — User Menu */}
        <div className="p-3 border-t border-gray-200 dark:border-gray-700">
          <UserMenu
            user={{ name: user?.name || 'Doctor', email: user?.email || '' }}
            onLogout={handleLogout}
          />
        </div>
      </aside>

      {/* Main Content */}
      <main
        className={cn(
          'min-h-screen transition-all duration-300 lg:ml-64',
          sidebarOpen ? 'lg:ml-64' : 'lg:ml-20'
        )}
      >
        {/* Top Bar */}
        <header className="sticky top-0 z-20 h-16 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm border-b border-gray-200 dark:border-gray-800">
          <div className="flex h-full items-center justify-between px-4 lg:px-6">
            {/* Left: Mobile menu + Search */}
            <div className="flex items-center gap-4 flex-1">
              <button
                className="lg:hidden p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
                onClick={() => setMobileMenuOpen(true)}
                aria-label="Open menu"
              >
                <Menu className="h-6 w-6" />
              </button>

              {/* Global Search + Command Palette Trigger */}
              <div className="relative flex-1 max-w-xl hidden sm:block">
                <PatientSearch
                  placeholder="Search patients... (⌘K)"
                  variant="header"
                  className="mb-0"
                />
                <button
                  onClick={openPalette}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded"
                  aria-label="Open command palette"
                  title="Command Palette (⌘K)"
                >
                  ⌘K
                </button>
              </div>
              <CommandPalette open={cmdPaletteOpen} onClose={closePalette} />
            </div>

            {/* Right: Actions */}
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                className="h-10 w-10 rounded-full text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                aria-label="Voice scheduling"
              >
                <Mic className="h-5 w-5" />
              </Button>

              <Button variant="ghost" size="icon" className="h-10 w-10 rounded-full relative">
                <Bell className="h-5 w-5" />
                <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-red-500" />
              </Button>

              <UserMenu
                user={{ name: user?.name || 'Doctor', email: user?.email || '' }}
                onLogout={handleLogout}
              />
            </div>
          </div>
        </header>

        {/* Page Content */}
        <div className="p-4 lg:p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}