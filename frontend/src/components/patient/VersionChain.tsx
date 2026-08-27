import { useMemo, useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/utils/helpers'
import { ChevronLeft, ChevronRight } from 'lucide-react'

// Version chain — chronological chain of colored circle nodes representing
// every version of the patient record. Hovering a node reveals a tooltip
// with the version's label, author, timestamp, and short summary. Clicking
// swaps the record view to that version.
//
// Node color encodes edit_type:
//   - initial    → primary-700 (deep teal)
//   - manual     → primary-500 (teal)
//   - ai_extract → accent-500 (mint)
//   - merge      → severity-moderate (amber)
//   - prescription → severity-high (orange)
//   - fallback   → primary-400
//
// The active node has a ring-2 primary-600 outline and a slight scale bump.
// The chain is horizontally scrollable when there are more nodes than the
// container can show — arrow buttons on either side page through it.

export interface VersionNode {
  version_number: number
  edit_type?: string
  author?: string
  timestamp?: string | null
  summary?: string
  label?: string
}

interface VersionChainProps {
  versions: VersionNode[]
  activeVersion: number | null
  onSelect: (v: number) => void
  onCompare?: (a: number, b: number) => void
  className?: string
}

// Central mapping of edit_type → node color. Keeping it out of the render
// path so the mapping is easy to eyeball and update.
const EDIT_TYPE_STYLE: Record<string, string> = {
  initial: 'bg-primary-700 ring-primary-800',
  manual: 'bg-primary-500 ring-primary-600',
  ai_extract: 'bg-accent-500 ring-accent-600',
  merge: 'bg-severity-moderate ring-orange-700',
  prescription: 'bg-severity-high ring-orange-700',
}
const DEFAULT_NODE_STYLE = 'bg-primary-400 ring-primary-500'

function nodeColorClass(editType?: string): string {
  if (!editType) return DEFAULT_NODE_STYLE
  return EDIT_TYPE_STYLE[editType] ?? DEFAULT_NODE_STYLE
}

function formatDate(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export function VersionChain({ versions, activeVersion, onSelect, className }: VersionChainProps) {
  const scrollerRef = useRef<HTMLDivElement | null>(null)
  const [tip, setTip] = useState<{ v: VersionNode; rect: DOMRect } | null>(null)

  // Sort ascending so the chain reads left-to-right in time order — the
  // store often returns newest-first for other views.
  const sorted = useMemo(
    () => [...versions].sort((a, b) => a.version_number - b.version_number),
    [versions]
  )

  // Auto-scroll the active node into view when it changes. Improves the
  // "I clicked v3 in the list, take me there in the chain too" flow.
  useEffect(() => {
    if (!activeVersion || !scrollerRef.current) return
    const node = scrollerRef.current.querySelector(`[data-vnode="${activeVersion}"]`)
    if (node) (node as HTMLElement).scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
  }, [activeVersion])

  const scrollBy = (dx: number) => {
    scrollerRef.current?.scrollBy({ left: dx, behavior: 'smooth' })
  }

  if (sorted.length === 0) {
    return (
      <div className={cn('text-sm text-muted-fg italic py-3', className)}>
        No versions yet. The first save will create v1.
      </div>
    )
  }

  return (
    <div className={cn('relative', className)}>
      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-label="Scroll versions left"
          onClick={() => scrollBy(-200)}
          className="p-1 rounded-md hover:bg-surface text-muted-fg hover:text-strong-fg transition-colors flex-shrink-0"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>

        <div
          ref={scrollerRef}
          className="flex-1 overflow-x-auto overflow-y-visible scrollbar-thin pb-2 pt-6"
        >
          <div className="relative flex items-center min-w-max px-2 pt-0 pb-4">
            {/* Chain connector — a thin horizontal rail that runs behind
                every node. Sits at the vertical center of the row. */}
            <div
              aria-hidden="true"
              className="absolute left-4 right-4 top-1/2 -translate-y-1/2 h-0.5 bg-border rounded-full"
            />

            {sorted.map((v) => {
              const isActive = activeVersion === v.version_number
              const colorClass = nodeColorClass(v.edit_type)
              return (
                <div
                  key={v.version_number}
                  className="relative flex flex-col items-center px-4"
                  onMouseEnter={(e) => setTip({ v, rect: e.currentTarget.getBoundingClientRect() })}
                  onMouseLeave={() => setTip(null)}
                >
                  <button
                    type="button"
                    data-vnode={v.version_number}
                    onClick={() => onSelect(v.version_number)}
                    aria-label={`Version ${v.version_number}${v.label ? ': ' + v.label : ''}`}
                    aria-pressed={isActive}
                    className={cn(
                      'relative z-10 rounded-full transition-all duration-150',
                      'flex items-center justify-center',
                      // Outer nested-circle effect: a lighter halo when the node
                      // is active — feels like "focus on this one".
                      isActive
                        ? 'h-10 w-10 ring-4 ring-primary-200 shadow-card-hover scale-110'
                        : 'h-7 w-7 ring-2 hover:scale-110 hover:ring-4 hover:ring-primary-100',
                      colorClass
                    )}
                  >
                    <span
                      className={cn(
                        'text-white font-semibold tnum leading-none',
                        isActive ? 'text-xs' : 'text-[10px]'
                      )}
                    >
                      {v.version_number}
                    </span>
                  </button>
                </div>
              )
            })}
          </div>
        </div>

        <button
          type="button"
          aria-label="Scroll versions right"
          onClick={() => scrollBy(200)}
          className="p-1 rounded-md hover:bg-surface text-muted-fg hover:text-strong-fg transition-colors flex-shrink-0"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      {/* Small legend so first-time viewers can read the color language. */}
      <div className="flex items-center gap-3 flex-wrap text-[11px] text-muted-fg mt-2 px-6">
        <LegendDot className="bg-primary-700" label="initial" />
        <LegendDot className="bg-primary-500" label="manual" />
        <LegendDot className="bg-accent-500" label="ai extract" />
        <LegendDot className="bg-severity-moderate" label="merge" />
        <LegendDot className="bg-severity-high" label="prescription" />
      </div>

      {/* Hover tooltip is rendered through a portal with fixed positioning so
          it is never clipped by the horizontally-scrolling chain container
          (whose overflow-y is forced to `auto` by overflow-x:auto). */}
      {tip &&
        createPortal(
          (() => {
            const w = 224
            const estH = 170
            const flipUp = tip.rect.bottom + estH + 12 > window.innerHeight
            const left = Math.min(
              Math.max(tip.rect.left + tip.rect.width / 2, w / 2 + 8),
              window.innerWidth - w / 2 - 8
            )
            const top = flipUp ? tip.rect.top - estH - 8 : tip.rect.bottom + 8
            return (
              <div
                role="tooltip"
                style={{ position: 'fixed', left, top, width: w, transform: 'translateX(-50%)', zIndex: 50 }}
                className="rounded-lg border border-border bg-surface-2 shadow-card-hover p-3 text-left animate-in"
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-sm font-semibold text-strong-fg">
                    v{tip.v.version_number}
                    {tip.v.label ? ` · ${tip.v.label}` : ''}
                  </span>
                  {tip.v.edit_type && (
                    <span className="text-[10px] uppercase tracking-wide font-medium text-muted-fg">
                      {tip.v.edit_type}
                    </span>
                  )}
                </div>
                {tip.v.summary && (
                  <p className="text-xs text-muted-fg mb-1 line-clamp-3">{tip.v.summary}</p>
                )}
                <div className="text-[10px] text-muted-fg flex items-center justify-between gap-2 pt-1 border-t border-border">
                  <span className="truncate">{tip.v.author || 'unknown'}</span>
                  <span className="tnum flex-shrink-0">{formatDate(tip.v.timestamp)}</span>
                </div>
              </div>
            )
          })(),
          document.body
        )}
    </div>
  )
}

function LegendDot({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={cn('h-2 w-2 rounded-full', className)} aria-hidden="true" />
      {label}
    </span>
  )
}
