'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/utils/helpers'
import { Loader2, CheckCircle2 } from 'lucide-react'

interface AgentTraceProps {
  events: string[]
  isStreaming: boolean
  onFinished?: boolean
}

function getColor(event: string): string {
  if (event.toLowerCase().includes('rout')) return 'text-purple-600 dark:text-purple-400'
  if (event.toLowerCase().includes('plan')) return 'text-blue-600 dark:text-blue-400'
  if (event.toLowerCase().includes('search') || event.toLowerCase().includes('record')) return 'text-cyan-600 dark:text-cyan-400'
  if (event.toLowerCase().includes('execut')) return 'text-orange-600 dark:text-orange-400'
  if (event.toLowerCase().includes('synth') || event.toLowerCase().includes('draft')) return 'text-green-600 dark:text-green-400'
  if (event.toLowerCase().includes('final')) return 'text-primary-600 dark:text-primary-400'
  return 'text-gray-600 dark:text-gray-400'
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
                  : 'bg-gray-50 dark:bg-gray-800/30'
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
