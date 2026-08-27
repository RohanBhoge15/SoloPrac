import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { apiClient } from '@/services/api'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: Date | string, options?: Intl.DateTimeFormatOptions): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    ...options,
  })
}

export function formatTime(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  })
}

export function formatDateTime(date: Date | string): string {
  return `${formatDate(date)} ${formatTime(date)}`
}

export function formatRelativeTime(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return formatDate(d)
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str
  return str.slice(0, length) + '...'
}

export function generateId(): string {
  return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15)
}

export function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

// D-7: Open a PDF in a new window and trigger the browser print dialog.
// The plain Download-style handler previously used for Print buttons never invoked print().
export function printPdfInNewWindow(url: string): void {
  const w = window.open(url, '_blank')
  if (!w) return
  // Some browsers (esp. Chrome PDF viewer) need a moment before print() works.
  const trigger = () => { try { w.focus(); w.print() } catch { /* noop */ } }
  w.addEventListener('load', trigger, { once: true })
  // Fallback for browsers that don't fire 'load' on PDF frames.
  setTimeout(trigger, 1200)
}

// R-6: Fetch a PDF through the axios apiClient (which handles auth cookies and
// the /api/v1 base URL) and open it as a blob URL. Callers used to hardcode
// `/api/v1/...` in `window.open`, which breaks under any proxy prefix change
// and skips the auth interceptor. Pass a path RELATIVE to /api/v1 (e.g.
// `/patient/me/prescriptions/${id}/pdf`).
export async function openPdfViaBlob(path: string): Promise<void> {
  const res = await apiClient.get(path, { responseType: 'blob' })
  const blob = new Blob([res.data], { type: 'application/pdf' })
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank')
  // Give the new tab time to load the blob before we release it.
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

// Same as openPdfViaBlob but triggers the browser print dialog on the opened tab.
export async function printPdfViaBlob(path: string): Promise<void> {
  const res = await apiClient.get(path, { responseType: 'blob' })
  const blob = new Blob([res.data], { type: 'application/pdf' })
  const url = URL.createObjectURL(blob)
  const w = window.open(url, '_blank')
  if (!w) return
  const trigger = () => { try { w.focus(); w.print() } catch { /* noop */ } }
  w.addEventListener('load', trigger, { once: true })
  setTimeout(trigger, 1200)
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

export function debounce<T extends (...args: unknown[]) => unknown>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => {
    if (timeout) clearTimeout(timeout)
    timeout = setTimeout(() => func(...args), wait)
  }
}