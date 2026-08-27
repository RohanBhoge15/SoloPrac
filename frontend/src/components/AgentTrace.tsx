'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/utils/helpers'
import { Loader2, CheckCircle2 } from 'lucide-react'

interface AgentTraceProps {
  events: string[]
  isStreaming: boolean
  onFinished?: boolean
}

const FRIENDLY_COLORS: Record<string, string> = {
  'Understanding your request…': 'text-primary-600',
  'Classifying your question…': 'text-purple-600',
  'Planning the steps…': 'text-blue-600',
  'Searching the patient record…': 'text-cyan-600',
  'Reviewing the draft…': 'text-orange-600',
  'Drafting the answer…': 'text-emerald-600',
  'Finalizing the response…': 'text-primary-600',
}
function getColor(event: string): string {
  if (FRIENDLY_COLORS[event]) return FRIENDLY_COLORS[event]
  const lower = event.toLowerCase()
  if (lower.includes('classif')) return 'text-purple-600'
  if (lower.includes('plan')) return 'text-blue-600'
  if (lower.includes('search') || lower.includes('record')) return 'text-cyan-600'
  if (lower.includes('review')) return 'text-orange-600'
  if (lower.includes('draft')) return 'text-emerald-600'
  if (lower.includes('final')) return 'text-primary-600'
  return 'text-muted-fg'
}

export function AgentTrace({ events, isStreaming }: AgentTraceProps) {
  if (events.length === 0) return null

  return (
    <div className="space-y-1.5 py-2">
      <AnimatePresence mode="popLayout">
        {events.map((event, idx) => {
          const isLast = idx === events.length - 1
          return (
            <motion.div
              key={`trace-${idx}`}
              initial={{ opacity: 0, x: -8, height: 0 }}
              animate={{ opacity: 1, x: 0, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className={cn(
                'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-colors',
                isLast && isStreaming
                  ? 'bg-primary-50 dark:bg-primary-900/10'
                  : 'bg-surface-3/50'
              )}
            >
              <span className="shrink-0">
                {isLast && isStreaming ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-primary-500" />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                )}
              </span>
              <span className={cn('font-medium', getColor(event))}>{event}</span>
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
