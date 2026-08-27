import { useEffect, useRef, useState } from 'react'
import { cn } from '@/utils/helpers'
import { Sparkles, Send, Loader2, StopCircle, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/Button'

// Copilot pane — dedicated per-patient AI chat pane that lives to the right
// of the patient record. Streams from POST /api/v1/agent/chat via SSE.
//
// EventSource can't do POST + credentials, so we do it manually with fetch
// + ReadableStream and parse the SSE frames ourselves. The three event
// types we handle:
//   - trace   → assistant "thinking" status line (transient)
//   - token   → append to the current assistant message
//   - done    → finalize the message + attach citations
//   - error   → surface the error inside the message list

// Hardcoded to match frontend/src/services/api.ts. Do NOT read
// import.meta.env.VITE_API_URL here — that var was deliberately removed from
// docker-compose (see AUDIT R-15) because nothing else reads it, so honouring
// it would make this one call diverge from every other request in the app.
const API_BASE = '/api/v1'

interface Citation {
  version_number?: number
  s3_key?: string
  title?: string
  score?: number
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  citations?: Citation[]
  status?: 'streaming' | 'done' | 'error'
  trace?: string
}

interface CopilotPaneProps {
  patientId: string
  patientName?: string
  onCiteVersion?: (v: number) => void
  className?: string
}

// Small helper — generates a locally-unique id. crypto.randomUUID exists in
// modern browsers; fall back to a timestamp for older ones.
function makeId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// Parses a chunk of SSE text into ordered (event, data) frames. SSE frames
// are separated by blank lines and use `event:` / `data:` prefixes.
function parseSseChunk(buffer: string): { frames: { event: string; data: string }[]; remainder: string } {
  const frames: { event: string; data: string }[] = []
  const parts = buffer.split(/\r?\n\r?\n/)
  const remainder = parts.pop() ?? ''
  for (const raw of parts) {
    let event = 'message'
    const dataLines: string[] = []
    for (const line of raw.split(/\r?\n/)) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    }
    if (dataLines.length > 0) frames.push({ event, data: dataLines.join('\n') })
  }
  return { frames, remainder }
}

export function CopilotPane({
  patientId,
  patientName,
  onCiteVersion,
  className,
}: CopilotPaneProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const conversationIdRef = useRef<string>(makeId())

  // Auto-scroll to the bottom whenever a new token arrives.
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages])

  // Cleanup — abort in-flight stream on unmount so we don't leak connections
  // when the doctor navigates away mid-answer.
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  const send = async () => {
    const q = input.trim()
    if (!q || sending) return

    const userMsg: Message = { id: makeId(), role: 'user', text: q, status: 'done' }
    const asstId = makeId()
    const asstMsg: Message = { id: asstId, role: 'assistant', text: '', status: 'streaming' }
    setMessages(m => [...m, userMsg, asstMsg])
    setInput('')
    setSending(true)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      // Fetch with retry on 401: refresh token then retry once
      let res = await fetch(`${API_BASE}/agent/chat`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify({
          query: q,
          patient_id: patientId,
          conversation_id: conversationIdRef.current,
        }),
        signal: ctrl.signal,
      })

      if (res.status === 401) {
        try {
          await fetch(`${API_BASE}/auth/refresh`, {
            method: 'POST',
            credentials: 'include',
          })
          res = await fetch(`${API_BASE}/agent/chat`, {
            method: 'POST',
            credentials: 'include',
            headers: {
              'Content-Type': 'application/json',
              'Accept': 'text/event-stream',
            },
            body: JSON.stringify({
              query: q,
              patient_id: patientId,
              conversation_id: conversationIdRef.current,
            }),
            signal: ctrl.signal,
          })
        } catch {}
      }

      if (!res.ok || !res.body) {
        const detail = res.headers.get('content-type')?.includes('application/json')
          ? (await res.json()).detail
          : await res.text()
        throw new Error(detail || `Request failed (${res.status})`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const { frames, remainder } = parseSseChunk(buffer)
        buffer = remainder
        for (const f of frames) {
          try {
            const parsed = JSON.parse(f.data)
            if (f.event === 'trace') {
              setMessages(m => m.map(x => x.id === asstId ? { ...x, trace: parsed.message } : x))
            } else if (f.event === 'token') {
              setMessages(m => m.map(x => x.id === asstId ? { ...x, text: x.text + (parsed.text || '') } : x))
            } else if (f.event === 'done') {
              setMessages(m => m.map(x => x.id === asstId
                ? {
                    ...x,
                    text: parsed.response || x.text,
                    citations: parsed.citations || [],
                    trace: undefined,
                    status: 'done',
                  }
                : x
              ))
            } else if (f.event === 'error') {
              setMessages(m => m.map(x => x.id === asstId
                ? { ...x, text: parsed.message || 'The assistant hit an error.', trace: undefined, status: 'error' }
                : x
              ))
            }
          } catch {
            // Non-JSON frame — ignore. The backend only emits JSON for the
            // events we handle; anything else is a keepalive or heartbeat.
          }
        }
      }
    } catch (err: any) {
      if (err?.name === 'AbortError') {
        // User cancelled — mark the streaming message as done with what we have.
        setMessages(m => m.map(x => x.id === asstId ? { ...x, status: 'done', trace: undefined } : x))
      } else {
        setMessages(m => m.map(x => x.id === asstId
          ? { ...x, text: err?.message || 'Failed to reach the assistant', status: 'error', trace: undefined }
          : x
        ))
      }
    } finally {
      setSending(false)
      abortRef.current = null
    }
  }

  const stop = () => {
    abortRef.current?.abort()
  }

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className={cn('flex flex-col h-full bg-surface-2 border border-border rounded-lg overflow-hidden', className)}>
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-surface">
        <div className="h-8 w-8 rounded-full bg-primary-100 flex items-center justify-center text-primary-700">
          <Sparkles className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-strong-fg">Clinical Copilot</div>
          <div className="text-[11px] text-muted-fg truncate">
            {patientName ? `Grounded to ${patientName}` : 'Grounded to this patient'}
          </div>
        </div>
      </div>

      {/* Message list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {messages.length === 0 && (
          <div className="text-sm text-muted-fg italic py-4">
            Ask a question about this patient — the assistant will search their record
            and cite the exact versions it used.
          </div>
        )}

        {messages.map(msg => (
          <div key={msg.id} className={cn('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div
              className={cn(
                'max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap',
                msg.role === 'user'
                  ? 'bg-primary-600 text-white'
                  : msg.status === 'error'
                    ? 'bg-red-50 text-severity-critical border border-red-200'
                    : 'bg-surface border border-border text-strong-fg'
              )}
            >
              {msg.status === 'error' && (
                <div className="flex items-center gap-1 mb-1 text-xs font-medium">
                  <AlertCircle className="h-3.5 w-3.5" /> Error
                </div>
              )}
              {msg.text || (msg.status === 'streaming' && !msg.trace && (
                <span className="italic text-muted-fg">Thinking…</span>
              ))}
              {msg.trace && msg.status === 'streaming' && (
                <div className="mt-1 text-[11px] text-muted-fg italic flex items-center gap-1">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  {msg.trace}
                </div>
              )}
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-2 pt-2 border-t border-border flex flex-wrap gap-1">
                  {msg.citations.map((c, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => c.version_number != null && onCiteVersion?.(c.version_number)}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-primary-50 text-primary-800 hover:bg-primary-100 border border-primary-200"
                      title={c.title || ''}
                    >
                      {c.version_number != null ? `v${c.version_number}` : (c.title || 'source')}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Input */}
      <div className="border-t border-border p-3 bg-surface">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="Ask about this patient…"
            rows={2}
            disabled={sending}
            className="flex-1 rounded-md border border-border bg-surface-2 px-3 py-2 text-sm text-strong-fg placeholder:text-muted-fg focus:outline-none focus:ring-2 focus:ring-primary-600/25 focus:border-primary-600 resize-none disabled:opacity-60"
          />
          {sending ? (
            <Button variant="outline" size="icon" onClick={stop} aria-label="Stop">
              <StopCircle className="h-4 w-4" />
            </Button>
          ) : (
            <Button size="icon" onClick={send} disabled={!input.trim()} aria-label="Send">
              <Send className="h-4 w-4" />
            </Button>
          )}
        </div>
        <div className="mt-1 text-[10px] text-muted-fg">
          Press Enter to send · Shift+Enter for newline
        </div>
      </div>
    </div>
  )
}
