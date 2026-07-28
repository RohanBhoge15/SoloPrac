'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { cn } from '@/utils/helpers'
import { Input } from '@/components/ui/Input'
import { Search, User, X, Loader2 } from 'lucide-react'
import apiClient from '@/services/api'

interface PatientSearchResult {
  id: string
  initials: string
  name: string
  age?: number
  gender?: string
  lastVisit?: string
}

interface PatientSearchProps {
  onSelect?: (patient: PatientSearchResult) => void
  placeholder?: string
  className?: string
  variant?: 'header' | 'sidebar'
}

export function PatientSearch({
  onSelect,
  placeholder = 'Search patients...',
  className,
  variant = 'header',
}: PatientSearchProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PatientSearchResult[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const debounceRef = useRef<NodeJS.Timeout | null>(null)

  const fetchPatients = useCallback(async (searchQuery: string) => {
    if (!searchQuery.trim()) {
      setResults([])
      return
    }
    setLoading(true)
    try {
      const res = await apiClient.get('/patients/search', { params: { q: searchQuery, limit: 15 } })
      const patients = (res.data ?? []).map((p: any) => {
        const demo = p.head_version?.state_jsonb?.demographics ?? {}
        const name = demo.name ?? `Patient ${p.id.slice(0, 8)}`
        return {
          id: p.id,
          initials: name.split(' ').map((n: string) => n[0]).join(''),
          name,
          age: demo.age,
          gender: demo.gender,
          lastVisit: p.updated_at ? new Date(p.updated_at).toLocaleDateString() : undefined,
        }
      })
      setResults(patients)
    } catch (e) {
      console.error('Patient search failed:', e)
      setResults([])
    } finally {
      setLoading(false)
    }
  }, [])

  const handleInputChange = (value: string) => {
    setQuery(value)
    setActiveIndex(-1)

    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      fetchPatients(value)
    }, 150)
  }

  const handleSelect = (patient: PatientSearchResult) => {
    setQuery('')
    setIsOpen(false)
    setResults([])
    onSelect?.(patient)
    navigate(`/patients/${patient.id}`)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) return

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setActiveIndex(prev => Math.min(prev + 1, results.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setActiveIndex(prev => Math.max(prev - 1, 0))
        break
      case 'Enter':
        e.preventDefault()
        if (activeIndex >= 0 && activeIndex < results.length) {
          handleSelect(results[activeIndex])
        }
        break
      case 'Escape':
        setIsOpen(false)
        setResults([])
        inputRef.current?.blur()
        break
    }
  }

  useEffect(() => {
    if (activeIndex >= 0 && listRef.current) {
      const item = listRef.current.children[activeIndex] as HTMLElement
      item?.scrollIntoView({ block: 'nearest' })
    }
  }, [activeIndex])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (!target.closest('[data-search-container]')) {
        setIsOpen(false)
        setActiveIndex(-1)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div
      data-search-container
      className={cn(
        'relative',
        variant === 'sidebar' && 'px-3 py-2',
        className
      )}
    >
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <Input
          ref={inputRef}
          type="search"
          value={query}
          onChange={e => handleInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => { if (results.length > 0) setIsOpen(true) }}
          placeholder={placeholder}
          aria-label="Search patients"
          aria-expanded={isOpen}
          aria-autocomplete="list"
          role="combobox"
          className={cn(
            'pl-10 pr-8 h-9 text-sm',
            variant === 'sidebar'
              ? 'bg-gray-100 dark:bg-gray-800 border-transparent focus:border-primary-500'
              : 'bg-gray-50 dark:bg-gray-800'
          )}
        />
        {query && (
          <button
            onClick={() => { setQuery(''); setResults([]); setIsOpen(false) }}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            aria-label="Clear search"
          >
            <X className="h-4 w-4" />
          </button>
        )}
        {loading && (
          <Loader2 className="absolute right-10 top-1/2 h-4 w-4 -translate-y-1/2 text-primary-500 animate-spin" />
        )}
      </div>

      {/* Results Dropdown */}
      {isOpen && results.length > 0 && (
        <div
          ref={listRef}
          className={cn(
            'absolute z-50 mt-1 w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg overflow-hidden',
            variant === 'sidebar' ? 'left-0' : ''
          )}
          role="listbox"
        >
          {results.map((patient, idx) => (
            <button
              key={patient.id}
              role="option"
              aria-selected={idx === activeIndex}
              onClick={() => handleSelect(patient)}
              onMouseEnter={() => setActiveIndex(idx)}
              className={cn(
                'flex items-center gap-3 w-full px-3 py-2.5 text-left transition-colors',
                idx === activeIndex
                  ? 'bg-primary-50 dark:bg-primary-900/20'
                  : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
              )}
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/30">
                <span className="text-xs font-medium text-primary-700 dark:text-primary-300">
                  {patient.initials}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                  {patient.name}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {patient.age ? `${patient.age} years` : ''}
                  {patient.gender ? ` · ${patient.gender}` : ''}
                  {patient.lastVisit ? ` · Last: ${patient.lastVisit}` : ''}
                </p>
              </div>
              <User className="h-4 w-4 text-gray-400 shrink-0" />
            </button>
          ))}
        </div>
      )}

      {/* No Results */}
      {isOpen && query && results.length === 0 && !loading && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg p-4 text-center">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No patients found for "{query}"
          </p>
        </div>
      )}
    </div>
  )
}