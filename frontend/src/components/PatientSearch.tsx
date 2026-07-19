'use client'

import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { cn } from '@/utils/helpers'
import { Input } from '@/components/ui/Input'
import { Search, User, X } from 'lucide-react'

interface PatientSearchResult {
  id: string
  initials: string
  name: string
  age?: number
  gender?: string
  lastVisit?: string
}

const MOCK_PATIENTS: PatientSearchResult[] = [
  { id: '1', initials: 'PS', name: 'Priya Sharma', age: 45, gender: 'Female', lastVisit: '2 days ago' },
  { id: '2', initials: 'RK', name: 'Rajesh Kumar', age: 32, gender: 'Male', lastVisit: 'Yesterday' },
  { id: '3', initials: 'AP', name: 'Anita Patel', age: 58, gender: 'Female', lastVisit: '1 week ago' },
  { id: '4', initials: 'MA', name: 'Mohammed Ali', age: 28, gender: 'Male', lastVisit: 'Today' },
  { id: '5', initials: 'SD', name: 'Sunita Devi', age: 41, gender: 'Female', lastVisit: '3 days ago' },
  { id: '6', initials: 'VK', name: 'Vikram Khanna', age: 35, gender: 'Male', lastVisit: '5 days ago' },
  { id: '7', initials: 'LP', name: 'Lata Patil', age: 62, gender: 'Female', lastVisit: '2 weeks ago' },
  { id: '8', initials: 'AJ', name: 'Arun Joshi', age: 50, gender: 'Male', lastVisit: '1 day ago' },
  { id: '9', initials: 'SS', name: 'Sneha Sharma', age: 27, gender: 'Female', lastVisit: 'Today' },
  { id: '10', initials: 'DK', name: 'Deepak Kulkarni', age: 55, gender: 'Male', lastVisit: '4 days ago' },
]

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
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  const filterPatients = (searchQuery: string) => {
    if (!searchQuery.trim()) {
      setResults([])
      return []
    }
    const q = searchQuery.toLowerCase()
    return MOCK_PATIENTS.filter(
      p =>
        p.name.toLowerCase().includes(q) ||
        p.initials.toLowerCase().includes(q)
    )
  }

  const handleInputChange = (value: string) => {
    setQuery(value)
    const filtered = filterPatients(value)
    setResults(filtered)
    setIsOpen(filtered.length > 0)
    setActiveIndex(-1)
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

  // Scroll active item into view
  useEffect(() => {
    if (activeIndex >= 0 && listRef.current) {
      const item = listRef.current.children[activeIndex] as HTMLElement
      item?.scrollIntoView({ block: 'nearest' })
    }
  }, [activeIndex])

  // Close on click outside
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
          onFocus={() => {
            if (results.length > 0) setIsOpen(true)
          }}
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
      {isOpen && query && results.length === 0 && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg p-4 text-center">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No patients found for "{query}"
          </p>
        </div>
      )}
    </div>
  )
}
