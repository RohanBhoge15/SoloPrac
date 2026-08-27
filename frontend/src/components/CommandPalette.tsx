'use client'

import { useState, useEffect, useCallback, useMemo, createContext, useContext, ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { cn } from '@/utils/helpers'
import {
  LayoutDashboard,
  Calendar,
  FileText,
  Settings,
  UserPlus,
  Upload,
  Users,
  Mic,
  TrendingUp,
  Search,
  Command,
  ArrowRight,
  type LucideIcon,
} from 'lucide-react'

interface CommandItem {
  id: string
  label: string
  description: string
  icon: LucideIcon
  action: () => void
  shortcut?: string
  category: string
}

interface CommandPaletteProps {
  open: boolean
  onClose: () => void
  // D-11 Part B: allow the palette's own ⌘K listener to open (not just close) the palette.
  onOpen?: () => void
}

export function CommandPalette({ open, onClose, onOpen }: CommandPaletteProps) {
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const navigate = useNavigate()

  const commands: CommandItem[] = [
    {
      id: 'go-dashboard',
      label: 'Go to Dashboard',
      description: 'View practice overview',
      icon: LayoutDashboard,
      action: () => navigate('/dashboard'),
      shortcut: 'G D',
      category: 'Navigation',
    },
    {
      id: 'go-calendar',
      label: 'Go to Calendar',
      description: 'View appointments and schedule',
      icon: Calendar,
      action: () => navigate('/calendar'),
      shortcut: 'G C',
      category: 'Navigation',
    },
    {
      id: 'go-scratchpad',
      label: 'Go to Scratchpad',
      description: 'Upload and process documents',
      icon: FileText,
      action: () => navigate('/scratchpad'),
      shortcut: 'G S',
      category: 'Navigation',
    },
    {
      id: 'go-settings',
      label: 'Go to Settings',
      description: 'Configure your practice',
      icon: Settings,
      action: () => navigate('/settings'),
      shortcut: 'G,',
      category: 'Navigation',
    },
    {
      id: 'new-patient',
      label: 'New Patient',
      description: 'Create a new patient record',
      icon: UserPlus,
      action: () => navigate('/dashboard?action=new-patient'),
      shortcut: 'N P',
      category: 'Actions',
    },
    {
      id: 'upload-document',
      label: 'Upload Document',
      description: 'Upload and process a medical document',
      icon: Upload,
      action: () => navigate('/scratchpad'),
      shortcut: 'U D',
      category: 'Actions',
    },
    {
      id: 'today-calendar',
      label: 'Today\'s Appointments',
      description: 'View today\'s schedule',
      icon: Calendar,
      action: () => navigate('/calendar'),
      shortcut: 'T',
      category: 'Actions',
    },
    {
      id: 'voice-scheduling',
      label: 'Voice Scheduling',
      description: 'Schedule appointments by voice',
      icon: Mic,
      action: () => navigate('/calendar?voice=true'),
      category: 'Actions',
    },
    {
      id: 'search-patients',
      label: 'Search Patients',
      description: 'Find a patient by name',
      icon: Users,
      action: () => {
        onClose()
        // Let the header mount settle, then focus the patient search via a11y label
        setTimeout(() => {
          const el =
            document.querySelector<HTMLInputElement>('[aria-label="Search patients"]') ||
            document.querySelector<HTMLInputElement>('input[type="search"]')
          el?.focus()
          el?.select()
        }, 80)
      },
      shortcut: '⌘K',
      category: 'Actions',
    },
    {
      id: 'weekly-reports',
      label: 'Weekly Reports',
      description: 'View AI-generated weekly summaries',
      icon: TrendingUp,
      // D-11 Part A: was navigating to /dashboard; route to actual weekly report page.
      action: () => navigate('/weekly-report'),
      category: 'Actions',
    },
  ]

  const filtered = useMemo(
    () =>
      query
        ? commands.filter(
            (cmd) =>
              cmd.label.toLowerCase().includes(query.toLowerCase()) ||
              cmd.description.toLowerCase().includes(query.toLowerCase()) ||
              (cmd.shortcut && cmd.shortcut.toLowerCase().includes(query.toLowerCase()))
          )
        : commands,
    // commands is stable (navigate is stable) — re-filter only on query
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [query]
  )

  // Reset index when query changes
  useEffect(() => {
    setActiveIndex(0)
  }, [query])

  const handleSelect = useCallback(
    (item: CommandItem) => {
      item.action()
      onClose()
      setQuery('')
    },
    [onClose]
  )

  const handleKeyDown = (e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setActiveIndex(prev => Math.min(prev + 1, filtered.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setActiveIndex(prev => Math.max(prev - 1, 0))
        break
      case 'Enter':
        e.preventDefault()
        if (filtered[activeIndex]) {
          handleSelect(filtered[activeIndex])
        }
        break
      case 'Escape':
        onClose()
        break
    }
  }

  // Global ⌘K / Ctrl+K listener
  // D-11 Part B: previously only closed the palette; now toggles (open if closed, close if open).
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        if (open) {
          onClose()
        } else if (onOpen) {
          onOpen()
        }
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose, onOpen])

  const grouped = useMemo(
    () =>
      filtered.reduce<Record<string, CommandItem[]>>((acc, item) => {
        if (!acc[item.category]) acc[item.category] = []
        acc[item.category].push(item)
        return acc
      }, {}),
    [filtered]
  )

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Palette */}
      <div
        className="fixed left-1/2 top-[15%] z-50 w-full max-w-lg -translate-x-1/2"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
      >
        <div className="rounded-xl border border-border bg-surface-2 shadow-card-elevated overflow-hidden">
          {/* Search Input */}
          <div className="flex items-center border-b border-border px-4">
            <Search className="h-5 w-5 text-muted-fg mr-3 shrink-0" />
            <input
              autoFocus
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search commands..."
              className="flex-1 h-14 bg-transparent text-strong-fg placeholder:text-muted-fg/60 outline-none text-[15px]"
              aria-label="Search commands"
            />
            <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-1 text-xs text-muted-fg bg-surface-3 rounded border border-border">
              <Command className="h-3 w-3" />
              K
            </kbd>
          </div>

          {/* Results */}
          <div className="max-h-80 overflow-y-auto py-2 px-2">
            {Object.entries(grouped).length === 0 ? (
              <div className="p-4 text-center text-sm text-gray-500">
                No commands found for "{query}"
              </div>
            ) : (
              Object.entries(grouped).map(([category, items]) => (
                <div key={category}>
                  <p className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                    {category}
                  </p>
                  {items.map((item) => {
                    const globalIdx = filtered.indexOf(item)
                    return (
                      <button
                        key={item.id}
                        onClick={() => handleSelect(item)}
                        onMouseEnter={() => setActiveIndex(globalIdx)}
                        className={cn(
                          'flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-left transition-colors',
                          globalIdx === activeIndex
                            ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
                            : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                        )}
                      >
                        <item.icon className="h-4 w-4 shrink-0 text-gray-400" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-900 dark:text-white">
                            {item.label}
                          </p>
                          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                            {item.description}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {item.shortcut && (
                            <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-mono text-gray-400 bg-gray-100 dark:bg-gray-800 rounded">
                              {item.shortcut}
                            </kbd>
                          )}
                          <ArrowRight className="h-3.5 w-3.5 text-gray-400" />
                        </div>
                      </button>
                    )
                  })}
                </div>
              ))
            )}
          </div>

          {/* Footer Hint */}
          <div className="border-t border-gray-200 dark:border-gray-700 px-4 py-2 flex items-center gap-4 text-xs text-gray-400">
            <span><kbd className="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 rounded">↑↓</kbd> Navigate</span>
            <span><kbd className="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 rounded">↵</kbd> Select</span>
            <span><kbd className="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 rounded">Esc</kbd> Close</span>
          </div>
        </div>
      </div>
    </>
  )
}

// ─── Global CommandProvider ────────────────────────
// Wrap this at the app level (inside AppLayout, which is the only layout that
// wants the palette) to provide ⌘K everywhere.
//
// Historical bug: this used to be a plain `useState` hook. Every component
// that called useCommandPalette() got its OWN private state — so the Dashboard's
// Search button was flipping a flag nobody was watching, and the palette
// (mounted in AppLayout with a different hook instance) never opened. Fixed
// by promoting to a real React Context; all consumers now share one truth.

interface CommandPaletteContextValue {
  isOpen: boolean
  toggle: () => void
  openPalette: () => void
  closePalette: () => void
}

const CommandPaletteContext = createContext<CommandPaletteContextValue | null>(null)

export function CommandPaletteProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false)
  const toggle = useCallback(() => setIsOpen(prev => !prev), [])
  const openPalette = useCallback(() => setIsOpen(true), [])
  const closePalette = useCallback(() => setIsOpen(false), [])
  return (
    <CommandPaletteContext.Provider value={{ isOpen, toggle, openPalette, closePalette }}>
      {children}
    </CommandPaletteContext.Provider>
  )
}

export function useCommandPalette(): CommandPaletteContextValue {
  const ctx = useContext(CommandPaletteContext)
  if (!ctx) {
    // Fall back to no-op so a stray caller outside the provider doesn't crash
    // the app. Warn loudly in dev so this is caught early.
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.warn('useCommandPalette() called outside CommandPaletteProvider — Search will not work here.')
    }
    return {
      isOpen: false,
      toggle: () => {},
      openPalette: () => {},
      closePalette: () => {},
    }
  }
  return ctx
}
