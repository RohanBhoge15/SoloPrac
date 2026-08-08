import { useMemo, useState } from 'react'
import { Pill, Beaker, Clock, Hash, Copy, Check } from 'lucide-react'
import { cn } from '@/utils/helpers'

/**
 * PrescriptionHighlighter — annotates raw OCR text with clinical entity tags.
 *
 * Backend OCR pipelines return `raw_text` but no bounding boxes we can trust
 * across engines (Docling / RapidOCR / MedGemma give different or no bbox
 * shapes). Rather than lie about spatial positions, we run a pure client-side
 * keyword pass that:
 *
 *   1. flags drug names, dosages, frequencies, and durations with distinct
 *      colored highlights on the ORIGINAL text (no bboxes, no image overlay);
 *   2. emits an entity summary sidebar the doctor can scan in seconds and copy
 *      to the clipboard.
 *
 * This is what most solo GPs actually want from OCR — "what did the prescription
 * say, structured?" — not a fancy image overlay.
 *
 * The regexes below are deliberately loose (recall > precision). Missing a
 * highlight is worse than an over-highlight because the doctor still verifies
 * the raw text.
 */

type EntityKind = 'drug' | 'dose' | 'frequency' | 'duration'

interface Entity {
  kind: EntityKind
  text: string
  start: number
  end: number
}

// ── Vocabulary ──
// Common Indian OTC / Rx drugs. Kept short on purpose — a full drug list would
// blow up the bundle. The regex prefixes are word-boundary so partial hits don't fire.
const COMMON_DRUGS = [
  'paracetamol', 'ibuprofen', 'aspirin', 'diclofenac', 'metformin', 'amoxicillin',
  'azithromycin', 'ciprofloxacin', 'ofloxacin', 'levocetirizine', 'cetirizine',
  'pantoprazole', 'omeprazole', 'ranitidine', 'famotidine', 'losartan', 'amlodipine',
  'atorvastatin', 'rosuvastatin', 'metoprolol', 'atenolol', 'telmisartan',
  'crocin', 'combiflam', 'dolo', 'sinarest', 'zyrtec', 'allegra', 'montair',
  'augmentin', 'zithromax', 'cipla', 'cifran', 'flagyl', 'metrogyl', 'metronidazole',
  'insulin', 'glimepiride', 'sitagliptin', 'ondansetron', 'domperidone',
]

const DRUG_RE = new RegExp(`\\b(${COMMON_DRUGS.join('|')})\\b`, 'gi')
// Dose: "500 mg", "5mg", "10 mcg", "1g", "2 ml", "500mg tab"
const DOSE_RE = /\b\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|iu|unit|units|tab|tablet|capsule|drops?)\b/gi
// Frequency: BD, TDS, OD, HS, PRN, 1-0-1, 2 times a day, every 6 hours
const FREQ_RE = /\b(?:od|bd|bid|tds|tid|qds|qid|hs|sos|prn|stat|once daily|twice(?:\s?a\s?day)?|thrice(?:\s?a\s?day)?|(?:every\s+)?\d+\s?(?:hours?|hrs?)|\d+-\d+-\d+)\b/gi
// Duration: "for 5 days", "x 7 days", "1 week", "2 weeks", "10 days"
const DUR_RE = /\b(?:for\s+)?(?:x\s?)?\d+\s?(?:days?|weeks?|months?|wks?)\b/gi

function extractEntities(text: string): Entity[] {
  const out: Entity[] = []
  const push = (kind: EntityKind, re: RegExp) => {
    re.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = re.exec(text)) !== null) {
      out.push({ kind, text: m[0], start: m.index, end: m.index + m[0].length })
    }
  }
  push('drug', DRUG_RE)
  push('dose', DOSE_RE)
  push('frequency', FREQ_RE)
  push('duration', DUR_RE)

  // Resolve overlaps: prefer earlier start, then longer match, then priority order.
  const priority: Record<EntityKind, number> = { drug: 0, dose: 1, frequency: 2, duration: 3 }
  const sorted = [...out].sort((a, b) => {
    if (a.start !== b.start) return a.start - b.start
    if (a.end - a.start !== b.end - b.start) return (b.end - b.start) - (a.end - a.start)
    return priority[a.kind] - priority[b.kind]
  })
  const kept: Entity[] = []
  let cursor = -1
  for (const ent of sorted) {
    if (ent.start >= cursor) { kept.push(ent); cursor = ent.end }
  }
  return kept
}

const KIND_STYLES: Record<EntityKind, { bg: string; text: string; ring: string; label: string; Icon: any }> = {
  drug:      { bg: 'bg-purple-100 dark:bg-purple-900/40',  text: 'text-purple-800 dark:text-purple-200',  ring: 'ring-purple-300',  label: 'Drug',      Icon: Pill },
  dose:      { bg: 'bg-blue-100 dark:bg-blue-900/40',      text: 'text-blue-800 dark:text-blue-200',      ring: 'ring-blue-300',    label: 'Dose',      Icon: Beaker },
  frequency: { bg: 'bg-amber-100 dark:bg-amber-900/40',    text: 'text-amber-800 dark:text-amber-200',    ring: 'ring-amber-300',   label: 'Frequency', Icon: Clock },
  duration:  { bg: 'bg-green-100 dark:bg-green-900/40',    text: 'text-green-800 dark:text-green-200',    ring: 'ring-green-300',   label: 'Duration',  Icon: Hash },
}

export interface PrescriptionHighlighterProps {
  text: string
  className?: string
}

export function PrescriptionHighlighter({ text, className }: PrescriptionHighlighterProps) {
  const entities = useMemo(() => extractEntities(text || ''), [text])
  const [activeIdx, setActiveIdx] = useState<number | null>(null)
  const [copied, setCopied] = useState(false)

  // Build the annotated JSX segments.
  const segments = useMemo(() => {
    if (entities.length === 0) return [{ kind: null, text }]
    const parts: Array<{ kind: EntityKind | null; text: string; entIdx?: number }> = []
    let cursor = 0
    entities.forEach((ent, i) => {
      if (ent.start > cursor) parts.push({ kind: null, text: text.slice(cursor, ent.start) })
      parts.push({ kind: ent.kind, text: text.slice(ent.start, ent.end), entIdx: i })
      cursor = ent.end
    })
    if (cursor < text.length) parts.push({ kind: null, text: text.slice(cursor) })
    return parts
  }, [text, entities])

  const groups = useMemo(() => {
    const g: Record<EntityKind, Entity[]> = { drug: [], dose: [], frequency: [], duration: [] }
    entities.forEach(e => g[e.kind].push(e))
    return g
  }, [entities])

  const copySummary = async () => {
    const lines = (['drug', 'dose', 'frequency', 'duration'] as EntityKind[])
      .filter(k => groups[k].length)
      .map(k => `${KIND_STYLES[k].label}: ${groups[k].map(e => e.text).join(', ')}`)
    try {
      await navigator.clipboard.writeText(lines.join('\n'))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard may be blocked in insecure contexts */ }
  }

  if (entities.length === 0) {
    // Empty state — fall back to plain rendering so caller can still show text.
    return (
      <pre className={cn('whitespace-pre-wrap font-mono text-sm', className)}>{text}</pre>
    )
  }

  return (
    <div className={cn('grid grid-cols-1 md:grid-cols-3 gap-4', className)}>
      {/* Highlighted text — 2 cols on desktop */}
      <div className="md:col-span-2 p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50 max-h-96 overflow-y-auto text-sm font-mono whitespace-pre-wrap leading-relaxed">
        {segments.map((seg, i) => {
          if (!seg.kind) return <span key={i}>{seg.text}</span>
          const s = KIND_STYLES[seg.kind]
          const isActive = activeIdx === seg.entIdx
          return (
            <mark
              key={i}
              onMouseEnter={() => setActiveIdx(seg.entIdx ?? null)}
              onMouseLeave={() => setActiveIdx(null)}
              className={cn(
                'px-1 py-0.5 rounded font-medium cursor-help transition-shadow',
                s.bg, s.text,
                isActive && `ring-2 ${s.ring}`
              )}
              title={s.label}
            >
              {seg.text}
            </mark>
          )
        })}
      </div>

      {/* Entity sidebar */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Extracted Fields</p>
          <button
            onClick={copySummary}
            className="text-xs text-primary-600 hover:underline flex items-center gap-1"
            aria-label="Copy summary"
          >
            {copied ? <><Check className="h-3 w-3" />Copied</> : <><Copy className="h-3 w-3" />Copy</>}
          </button>
        </div>

        {(['drug', 'dose', 'frequency', 'duration'] as EntityKind[]).map(kind => {
          const list = groups[kind]
          if (list.length === 0) return null
          const s = KIND_STYLES[kind]
          const Icon = s.Icon
          return (
            <div key={kind}>
              <p className="text-xs text-gray-500 flex items-center gap-1 mb-1">
                <Icon className={cn('h-3 w-3', s.text)} />
                <span>{s.label}</span>
                <span className="text-gray-400">· {list.length}</span>
              </p>
              <div className="flex flex-wrap gap-1">
                {list.map((ent, i) => {
                  const globalIdx = entities.indexOf(ent)
                  const isActive = activeIdx === globalIdx
                  return (
                    <button
                      key={i}
                      onMouseEnter={() => setActiveIdx(globalIdx)}
                      onMouseLeave={() => setActiveIdx(null)}
                      className={cn(
                        'px-2 py-0.5 rounded-full text-xs font-medium transition-shadow',
                        s.bg, s.text,
                        isActive && `ring-2 ${s.ring}`
                      )}
                    >
                      {ent.text}
                    </button>
                  )
                })}
              </div>
            </div>
          )
        })}

        <p className="text-[10px] text-gray-400 italic pt-2 border-t border-gray-200 dark:border-gray-700">
          Highlights are pattern-based; always verify against the original document.
        </p>
      </div>
    </div>
  )
}
