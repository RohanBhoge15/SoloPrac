'use client'

import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/utils/helpers'
import { formatDistanceToNow } from 'date-fns'
import { Clock, User, Bot, FileScan, GitBranch, ArrowLeftRight } from 'lucide-react'

export interface VersionNode {
  id: string
  version_number: number
  author: string
  edit_type: 'manual' | 'voice' | 'ocr' | 'ai_suggestion' | 'revert'
  summary: string
  tags: string[]
  clinical_significance: number
  timestamp: string
}

interface TimelineScrubberProps {
  versions: VersionNode[]
  activeVersion: number | null
  onSelectVersion: (version: number) => void
  onCompare: (v1: number, v2: number) => void
}

const EDIT_TYPE_ICONS: Record<string, React.ElementType> = {
  manual: User,
  voice: Clock,
  ocr: FileScan,
  ai_suggestion: Bot,
  revert: GitBranch,
}

const EDIT_TYPE_LABELS: Record<string, string> = {
  manual: 'Manual',
  voice: 'Voice',
  ocr: 'OCR',
  ai_suggestion: 'AI',
  revert: 'Revert',
}

function getColor(version: VersionNode): string {
  if (version.author.startsWith('doctor:')) return 'bg-blue-500'
  if (version.author.startsWith('agent:')) return 'bg-purple-500'
  return 'bg-gray-400'
}

function getNodeSize(version: VersionNode): string {
  if (version.edit_type === 'ai_suggestion') return 'h-5 w-5'
  return 'h-4 w-4'
}

export function TimelineScrubber({
  versions,
  activeVersion,
  onSelectVersion,
  onCompare,
}: TimelineScrubberProps) {
  const [hoveredVersion, setHoveredVersion] = useState<number | null>(null)
  const [selectedCompare, setSelectedCompare] = useState<number | null>(null)
  const [showCompare, setShowCompare] = useState(false)

  // Auto-scroll to active version
  useEffect(() => {
    if (activeVersion) {
      const el = document.querySelector(`[data-ver="${activeVersion}"]`)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }
  }, [activeVersion])

  if (!versions.length) {
    return (
      <div className="p-6 text-center text-gray-500 dark:text-gray-400 text-sm">
        No version history available.
      </div>
    )
  }

  // Sort ascending for timeline display (oldest left, newest right)
  const sorted = [...versions].sort((a, b) => a.version_number - b.version_number)

  return (
    <div className="relative select-none">
      {/* Compare toggle */}
      <div className="flex items-center justify-end mb-2 gap-2">
        <button
          onClick={() => { setShowCompare(!showCompare); setSelectedCompare(null) }}
          className={cn(
            'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
            showCompare
              ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
              : 'bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400'
          )}
        >
          <ArrowLeftRight className="h-3.5 w-3.5" />
          Compare
        </button>
      </div>

      {/* Timeline track */}
      <div
        className="flex items-center gap-0 overflow-x-auto py-3 px-2 scrollbar-thin"
      >
        {/* Connecting line background */}
        <div className="absolute top-1/2 left-0 right-0 h-0.5 bg-gray-200 dark:bg-gray-700 -translate-y-1/2 z-0" />

        {sorted.map((version, idx) => {
          const isActive = activeVersion === version.version_number
          const isHovered = hoveredVersion === version.version_number
          const isCompareSelected = selectedCompare === version.version_number
          const color = getColor(version)
          const Icon = EDIT_TYPE_ICONS[version.edit_type] || GitBranch

          return (
            <div key={version.id} className="relative flex flex-col items-center z-10 min-w-[40px]">
              {/* Version node */}
              <motion.button
                data-ver={version.version_number}
                whileHover={{ scale: 1.2 }}
                whileTap={{ scale: 0.95 }}
                onMouseEnter={() => setHoveredVersion(version.version_number)}
                onMouseLeave={() => setHoveredVersion(null)}
                onClick={() => {
                  if (showCompare && selectedCompare === null) {
                    setSelectedCompare(version.version_number)
                  } else if (showCompare && selectedCompare !== null) {
                    onCompare(selectedCompare, version.version_number)
                    setShowCompare(false)
                    setSelectedCompare(null)
                  } else {
                    onSelectVersion(version.version_number)
                  }
                }}
                className={cn(
                  'relative rounded-full flex items-center justify-center border-2 border-white dark:border-gray-800 shadow-sm transition-shadow',
                  color,
                  isActive && 'ring-2 ring-offset-2 ring-primary-500 dark:ring-offset-gray-950 scale-110',
                  isCompareSelected && 'ring-2 ring-offset-2 ring-yellow-500 dark:ring-offset-gray-950',
                  getNodeSize(version),
                )}
                title={`v${version.version_number} · ${EDIT_TYPE_LABELS[version.edit_type]}`}
              >
                {isActive && (
                  <motion.div
                    layoutId="activeNode"
                    className="absolute inset-0 rounded-full bg-white/30"
                    transition={{ type: 'spring', stiffness: 300, damping: 20 }}
                  />
                )}
              </motion.button>

              {/* Version number below */}
              <span
                className={cn(
                  'mt-1.5 text-[10px] font-mono font-medium transition-colors',
                  isActive
                    ? 'text-primary-600 dark:text-primary-400'
                    : 'text-gray-500 dark:text-gray-400'
                )}
              >
                v{version.version_number}
              </span>

              {/* Edit type icon below version number (non-active) */}
              {version.edit_type !== 'manual' && !isActive && (
                <Icon className="h-3 w-3 text-gray-400 mt-0.5" />
              )}

              {/* Hover tooltip */}
              <AnimatePresence>
                {isHovered && (
                  <motion.div
                    initial={{ opacity: 0, y: 8, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 8, scale: 0.95 }}
                    transition={{ duration: 0.15 }}
                    className="absolute bottom-full mb-3 w-48 p-3 rounded-lg bg-white dark:bg-gray-800 shadow-lg border border-gray-200 dark:border-gray-700 z-50 pointer-events-none"
                  >
                    <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                      {version.summary || `Version ${version.version_number}`}
                    </p>
                    <div className="flex items-center gap-2 mt-1.5">
                      <span className={cn(
                        'text-[10px] px-1.5 py-0.5 rounded font-medium',
                        version.edit_type === 'manual' && 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
                        version.edit_type === 'ai_suggestion' && 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
                        version.edit_type === 'ocr' && 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
                        version.edit_type === 'revert' && 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
                        version.edit_type === 'voice' && 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
                      )}>
                        {EDIT_TYPE_LABELS[version.edit_type]}
                      </span>
                      <span className="text-[10px] text-gray-400">
                        {formatDistanceToNow(new Date(version.timestamp), { addSuffix: true })}
                      </span>
                    </div>
                    {version.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {version.tags.slice(0, 3).map((tag) => (
                          <span key={tag} className="text-[9px] px-1 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 rounded">
                            {tag}
                          </span>
                        ))}
                        {version.tags.length > 3 && (
                          <span className="text-[9px] text-gray-400">+{version.tags.length - 3}</span>
                        )}
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Connector line between nodes */}
              {idx < sorted.length - 1 && (
                <div className="absolute top-1/2 left-[60%] w-full h-0.5 bg-gray-300 dark:bg-gray-600 -z-10" />
              )}
            </div>
          )
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-2 px-2 text-[10px] text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-full bg-blue-500" /> Doctor
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-full bg-purple-500" /> AI
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-full bg-gray-400" /> OCR/Voice
        </span>
      </div>
    </div>
  )
}