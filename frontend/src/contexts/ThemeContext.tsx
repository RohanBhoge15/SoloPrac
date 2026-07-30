import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'soloprac_theme'

interface ThemeContextType {
  /** The user's stored preference — may be 'system'. */
  mode: ThemeMode
  /** The theme actually applied to <html>, after resolving 'system'. */
  resolved: 'light' | 'dark'
  setMode: (mode: ThemeMode) => void
  /** Cycles light → dark → system. */
  cycleMode: () => void
  /** Flips between light and dark (pins the choice, leaving 'system'). */
  toggle: () => void
}

const ThemeContext = createContext<ThemeContextType | null>(null)

function readStoredMode(): ThemeMode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  } catch {
    // localStorage unavailable (private mode / SSR) — fall back to system
  }
  return 'system'
}

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-color-scheme: dark)').matches
}

function applyTheme(resolved: 'light' | 'dark') {
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')
  root.style.colorScheme = resolved
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readStoredMode)
  const [systemDark, setSystemDark] = useState<boolean>(systemPrefersDark)

  // Track OS-level changes so 'system' stays live.
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  const resolved: 'light' | 'dark' = mode === 'system' ? (systemDark ? 'dark' : 'light') : mode

  useEffect(() => {
    applyTheme(resolved)
  }, [resolved])

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Preference can't be persisted; the in-memory choice still applies.
    }
  }, [])

  const cycleMode = useCallback(() => {
    setMode(mode === 'light' ? 'dark' : mode === 'dark' ? 'system' : 'light')
  }, [mode, setMode])

  const toggle = useCallback(() => {
    setMode(resolved === 'dark' ? 'light' : 'dark')
  }, [resolved, setMode])

  return (
    <ThemeContext.Provider value={{ mode, resolved, setMode, cycleMode, toggle }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider')
  return ctx
}

/**
 * Applies the persisted theme before React mounts so there is no
 * light-mode flash on first paint.
 */
export function initTheme() {
  const mode = readStoredMode()
  applyTheme(mode === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : mode)
}
