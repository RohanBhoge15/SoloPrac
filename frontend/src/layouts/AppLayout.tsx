import { useState, useEffect, useRef } from 'react'
import { Link, useLocation, useNavigate, Outlet } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { cn } from '@/utils/helpers'
import { Button } from '@/components/ui/Button'
import { UserMenu } from '@/components/layout/UserMenu'
import { PatientSearch } from '@/components/PatientSearch'
import { Breadcrumbs } from '@/components/layout/Breadcrumbs'
import { CommandPalette, useCommandPalette, CommandPaletteProvider } from '@/components/CommandPalette'
import { useAuth } from '@/contexts/AuthContext'
import { apiClient } from '@/services/api'
import { useDoctorWebSocket } from '@/hooks/useWebSocket'
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

// C-9 (Piece 6): doctor-side inbox item shape returned by /doctor/me/inbox.
interface DoctorInboxItem {
  id: string
  kind: string
  subject: string
  body: string
  meta: Record<string, any> | null
  read: boolean
  patient_id: string | null
  created_at: string | null
}

// Small "12m ago" formatter — no runtime dep. Handles null gracefully.
function relTime(iso: string | null): string {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const diff = Math.max(0, Date.now() - then)
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

const NAV_ITEMS = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/chat', label: 'AI Assistant', icon: MessageSquare },
  { path: '/calendar', label: 'Calendar', icon: Calendar },
  { path: '/scratchpad', label: 'Scratchpad', icon: FileText },
  { path: '/settings', label: 'Settings', icon: Settings },
]

// Outer component provides the CommandPalette context so BOTH the AppLayout
// header (which mounts <CommandPalette/>) and the routed page below (via
// <Outlet/>) share the same open/close state. Previously each caller of
// useCommandPalette() got its own private useState — that's why the
// Dashboard Search button did nothing.
export function AppLayout() {
  return (
    <CommandPaletteProvider>
      <AppLayoutInner />
    </CommandPaletteProvider>
  )
}

function AppLayoutInner() {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const queryClient = useQueryClient()
  const [sidebarOpen] = useState(true)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [notifOpen, setNotifOpen] = useState(false)
  const notifRef = useRef<HTMLDivElement | null>(null)
  const { isOpen: cmdPaletteOpen, openPalette, closePalette } = useCommandPalette()

  // C-9 (Piece 6): lifted from Dashboard so notifications stream on every page.
  // On any "notification" WS event, invalidate the inbox queries so the bell
  // count and list refresh without waiting for the 30s poll.
  const { lastEvent } = useDoctorWebSocket(user?.id ?? null)
  useEffect(() => {
    if (lastEvent?.type === 'notification') {
      queryClient.invalidateQueries({ queryKey: ['doctor-inbox-unread'] })
      queryClient.invalidateQueries({ queryKey: ['doctor-inbox'] })
    }
  }, [lastEvent, queryClient])

  // C-9 (Piece 6): unread-count drives the red dot on the bell. Polls every
  // 30s as a safety net when the WS is dropped between reconnects.
  const { data: unreadData } = useQuery<{ count: number }>({
    queryKey: ['doctor-inbox-unread'],
    queryFn: async () => {
      const res = await apiClient.get('/doctor/me/inbox/unread-count')
      return res.data as { count: number }
    },
    enabled: !!user?.id,
    refetchInterval: 30_000,
    staleTime: 15_000,
  })
  const unreadCount = unreadData?.count ?? 0

  // C-9 (Piece 6): fetch the list only when the popover is open, so we
  // don't hammer the endpoint for users who never look at their inbox.
  const { data: inboxItems, isLoading: inboxLoading } = useQuery<DoctorInboxItem[]>({
    queryKey: ['doctor-inbox'],
    queryFn: async () => {
      const res = await apiClient.get('/doctor/me/inbox?limit=15')
      return res.data as DoctorInboxItem[]
    },
    enabled: !!user?.id && notifOpen,
    staleTime: 10_000,
  })

  const markRead = async (id: string) => {
    try {
      await apiClient.patch(`/doctor/me/inbox/${id}/read`)
      queryClient.invalidateQueries({ queryKey: ['doctor-inbox-unread'] })
      queryClient.invalidateQueries({ queryKey: ['doctor-inbox'] })
    } catch {
      // Non-fatal — user can retry
    }
  }

  const openItem = (n: DoctorInboxItem) => {
    setNotifOpen(false)
    if (!n.read) markRead(n.id)
    const rt = n.meta?.resource_type
    if (rt === 'appointment') {
      navigate('/calendar')
    } else if (rt === 'patient') {
      const pid = n.meta?.resource_id || n.patient_id
      if (pid) navigate(`/patients/${pid}`)
    }
  }

  // Close the notifications popover on outside-click. Bound only when open so
  // we're not paying a global listener on every route.
  useEffect(() => {
    if (!notifOpen) return
    const onDown = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [notifOpen])

  // Global Cmd/Ctrl+K opens the palette from anywhere in the app.
  // The palette component itself handles Cmd+K → close when it's already open,
  // so we only fire this when the palette is closed to avoid a double-toggle race.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        // Don't hijack Cmd+K inside inputs where users might expect native behavior.
        const target = e.target as HTMLElement | null
        const tag = target?.tagName?.toLowerCase()
        const editable = tag === 'input' || tag === 'textarea' || target?.isContentEditable
        if (editable && !cmdPaletteOpen) {
          // Still open the palette — Cmd+K in a search bar is what most apps do — but
          // let inputs that specifically opt-out (data-no-cmdk) keep the native behavior.
          if (target?.dataset?.noCmdk !== undefined) return
        }
        if (!cmdPaletteOpen) {
          e.preventDefault()
          openPalette()
        }
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [cmdPaletteOpen, openPalette])

  const handleLogout = () => {
    logout()
  }

  return (
    <div className="min-h-screen bg-surface">
      {/* Mobile menu overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed left-0 top-0 z-30 h-screen bg-surface-2 border-r border-border transition-all duration-300 lg:translate-x-0',
          sidebarOpen ? 'w-64' : 'w-20',
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        )}
      >
        {/* Logo / Brand */}
        <div className="flex h-16 items-center justify-between px-4 border-b border-border">
          <Link to="/dashboard" className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-600 shadow-card">
              <span className="text-white font-bold text-sm tracking-tight">SP</span>
            </div>
            {sidebarOpen && (
              <span className="font-semibold text-base text-strong-fg tracking-tight">
                SoloPrac<span className="text-primary-600"> AI</span>
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
                  'group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-200'
                    : 'text-muted-fg hover:bg-surface hover:text-strong-fg',
                  sidebarOpen ? 'justify-start' : 'justify-center'
                )}
                title={sidebarOpen ? undefined : item.label}
              >
                {isActive && (
                  <span
                    aria-hidden="true"
                    className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-1 rounded-r bg-primary-600"
                  />
                )}
                <item.icon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
                {sidebarOpen && <span>{item.label}</span>}
              </Link>
            )
          })}

          {/* Quick Actions Section */}
          {sidebarOpen && (
            <div className="pt-4 mt-4 border-t border-border">
              <h3 className="px-3 text-[11px] font-semibold text-muted-fg uppercase tracking-wider">
                Quick Actions
              </h3>
              <div className="mt-2 space-y-1">
                {/* Sidebar quick actions — the audit flagged these four buttons
                    as no-op stubs. "New Patient" goes to the manual walk-in
                    form (India context: most patients don't self-register;
                    backend auto-links by phone if they sign up later).
                    "Upload Document" opens Scratchpad. */}
                <Button
                  variant="ghost"
                  className="w-full justify-start gap-2"
                  size="sm"
                  onClick={() => navigate('/patients/new')}
                >
                  <Plus className="h-4 w-4" />
                  <span>New Patient</span>
                </Button>
                <Button
                  variant="ghost"
                  className="w-full justify-start gap-2"
                  size="sm"
                  onClick={() => navigate('/scratchpad')}
                >
                  <FileText className="h-4 w-4" />
                  <span>Upload Document</span>
                </Button>
                <Button
                  variant="ghost"
                  className="w-full justify-start gap-2"
                  size="sm"
                  onClick={() => navigate('/calendar')}
                >
                  <Calendar className="h-4 w-4" />
                  <span>Today's Calendar</span>
                </Button>
                <Button
                  variant="ghost"
                  className="w-full justify-start gap-2"
                  size="sm"
                  onClick={() => navigate('/weekly-report')}
                >
                  <Bell className="h-4 w-4" />
                  <span>Weekly Reports</span>
                </Button>
              </div>
            </div>
          )}
        </nav>

        {/* User menu lives top-right in the header — removed the sidebar-bottom
            copy so we don't ship two identical profile dropdowns on every page. */}
      </aside>

      {/* Main Content */}
      <main
        className={cn(
          'min-h-screen transition-all duration-300 lg:ml-64',
          sidebarOpen ? 'lg:ml-64' : 'lg:ml-20'
        )}
      >
        {/* Top Bar */}
        <header className="sticky top-0 z-20 h-16 bg-surface-2/85 backdrop-blur-md border-b border-border">
          <div className="flex h-full items-center justify-between px-4 lg:px-6">
            {/* Left: Mobile menu + Search */}
            <div className="flex items-center gap-4 flex-1">
              <button
                className="lg:hidden p-2 rounded-md hover:bg-surface"
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
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-[11px] font-medium text-muted-fg hover:text-strong-fg bg-surface border border-border px-1.5 py-0.5 rounded"
                  aria-label="Open command palette"
                  title="Command Palette (⌘K)"
                >
                  ⌘K
                </button>
              </div>
              <CommandPalette open={cmdPaletteOpen} onClose={closePalette} onOpen={openPalette} />
            </div>

            {/* Right: Actions */}
            <div className="flex items-center gap-2">
              {/* Voice → jumps to the calendar; scheduling by voice happens there. */}
              <Button
                variant="ghost"
                size="icon"
                onClick={() => navigate('/calendar')}
                className="h-10 w-10 rounded-full text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                aria-label="Voice scheduling"
                title="Voice scheduling — opens calendar"
              >
                <Mic className="h-5 w-5" />
              </Button>

              {/* C-9 (Piece 6): live doctor-side notification bell.
                  Red dot appears when unreadCount > 0. Popover fetches the
                  most recent 15 rows from /doctor/me/inbox and renders them
                  with a Mark-as-read affordance. */}
              <div className="relative" ref={notifRef}>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setNotifOpen(v => !v)}
                  className="h-10 w-10 rounded-full relative"
                  aria-label={unreadCount > 0 ? `Notifications (${unreadCount} unread)` : 'Notifications'}
                  aria-expanded={notifOpen}
                >
                  <Bell className="h-5 w-5" />
                  {unreadCount > 0 && (
                    <span
                      className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] rounded-full bg-red-500 text-white text-[10px] font-semibold flex items-center justify-center px-1"
                      aria-hidden="true"
                    >
                      {unreadCount < 10 ? unreadCount : '9+'}
                    </span>
                  )}
                </Button>
                {notifOpen && (
                  <div className="absolute right-0 top-12 z-50 w-80 rounded-lg border border-border bg-surface-2 shadow-card-hover overflow-hidden">
                    <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                      <div className="text-sm font-semibold text-strong-fg">
                        Notifications
                      </div>
                      {unreadCount > 0 && (
                        <span className="text-xs text-muted-fg">
                          {unreadCount} unread
                        </span>
                      )}
                    </div>

                    <div className="max-h-96 overflow-y-auto">
                      {inboxLoading && (
                        <p className="p-4 text-xs text-muted-fg">Loading…</p>
                      )}
                      {!inboxLoading && (!inboxItems || inboxItems.length === 0) && (
                        <p className="p-4 text-xs text-muted-fg">
                          You're all caught up — no new alerts.
                        </p>
                      )}
                      {!inboxLoading && inboxItems && inboxItems.map((n) => (
                        <div
                          key={n.id}
                          onClick={() => openItem(n)}
                          className={cn(
                            'px-4 py-3 border-b border-border cursor-pointer hover:bg-surface',
                            !n.read && 'bg-primary-50/40 dark:bg-primary-900/10'
                          )}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <div className="text-sm font-semibold text-strong-fg truncate">
                                {n.subject}
                              </div>
                              <div
                                className="mt-0.5 text-xs text-muted-fg"
                                style={{
                                  display: '-webkit-box',
                                  WebkitLineClamp: 2,
                                  WebkitBoxOrient: 'vertical',
                                  overflow: 'hidden',
                                }}
                              >
                                {n.body}
                              </div>
                              <div className="mt-1 text-[10px] text-muted-fg opacity-75">
                                {relTime(n.created_at)}
                              </div>
                            </div>
                            {!n.read && (
                              <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); markRead(n.id) }}
                                className="text-[10px] font-medium text-primary-700 hover:underline whitespace-nowrap"
                              >
                                Mark as read
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="border-t border-border px-4 py-3">
                      <button
                        type="button"
                        onClick={() => { setNotifOpen(false); navigate('/settings?tab=notifications') }}
                        className="text-xs font-medium text-primary-700 hover:underline"
                      >
                        Manage notification preferences →
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <UserMenu
                user={{ name: user?.name || 'Doctor', email: user?.email || '' }}
                onLogout={handleLogout}
              />
            </div>
          </div>
        </header>

        {/* Page Content */}
        <div className="p-4 lg:p-6">
          <Breadcrumbs />
          <Outlet />
        </div>
      </main>
    </div>
  )
}