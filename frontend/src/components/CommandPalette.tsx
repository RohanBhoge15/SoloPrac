'use client'

import { useState, useEffect, useCallback } from 'react'
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
}

export function CommandPalette({ open, onClose }: CommandPaletteProps) {
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
        // Focus the search input in the header
        const searchInput = document.querySelector<HTMLInputElement>('input[type="search"]')
        searchInput?.focus()
        onClose()
      },
      shortcut: '⌘K',
      category: 'Actions',
    },
    {
      id: 'weekly-reports',
      label: 'Weekly Reports',
      description: 'View AI-generated weekly summaries',
      icon: TrendingUp,
      action: () => navigate('/dashboard'),
      category: 'Actions',
    },
  ]

  const filtered = query
    ? commands.filter(
        cmd =>
          cmd.label.toLowerCase().includes(query.toLowerCase()) ||
          cmd.description.toLowerCase().includes(query.toLowerCase()) ||
          (cmd.shortcut && cmd.shortcut.toLowerCase().includes(query.toLowerCase()))
      )
    : commands

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
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        if (open) {
          onClose()
        }
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  // Group by category
  const grouped = filtered.reduce<Record<string, CommandItem[]>>((acc, item) => {
    if (!acc[item.category]) acc[item.category] = []
    acc[item.category].push(item)
    return acc
  }, {})

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
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-2xl overflow-hidden">
          {/* Search Input */}
          <div className="flex items-center border-b border-gray-200 dark:border-gray-700 px-4">
            <Search className="h-5 w-5 text-gray-400 mr-3 shrink-0" />
            <input
              autoFocus
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search commands..."
              className="flex-1 h-14 bg-transparent text-gray-900 dark:text-white placeholder-gray-400 outline-none text-lg"
              aria-label="Search commands"
            />
            <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-1 text-xs text-gray-400 bg-gray-100 dark:bg-gray-800 rounded">
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
// Wrap this at the app level to provide ⌘K everywhere

export function useCommandPalette() {
  const [isOpen, setIsOpen] = useState(false)

  const toggle = useCallback(() => setIsOpen(prev => !prev), [])
  const openPalette = useCallback(() => setIsOpen(true), [])
  const closePalette = useCallback(() => setIsOpen(false), [])

  return { isOpen, toggle, openPalette, closePalette }
}
