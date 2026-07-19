'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/utils/helpers'
import { Button } from '@/components/ui/Button'
import { AgentTrace } from '@/components/AgentTrace'
import { useSSE } from '@/hooks/useSSE'
import {
  Send,
  Mic,
  Square,
  Bot,
  User,
  AlertCircle,
  Loader2,
  Sparkles,
  GitCommit,
  ExternalLink,
} from 'lucide-react'

interface Citation {
  version_number: number
  date: string
  summary: string
  score?: number
  edit_type?: string
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  isStreaming?: boolean
  trace?: string[]
  citations?: Citation[]
}

interface ChatUIProps {
  patientId?: string
  className?: string
  initialMessage?: string
  onCiteVersion?: (versionNumber: number) => void
}

function renderContentWithCitations(
  content: string,
  citations: Citation[] | undefined,
  onCiteVersion?: (versionNumber: number) => void,
): React.ReactNode {
  if (!citations || citations.length === 0) {
    return <div className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap">{content}</div>
  }

  // Replace [v{n} · {date}] patterns with clickable chips and render the rest as prose
  const parts = content.split(/(\[v\d+\s*·\s*[\d-]+\])/g)

  return (
    <div className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap">
      {parts.map((part, i) => {
        const match = part.match(/\[v(\d+)\s*·\s*([\d-]+)\]/)
        if (match) {
          const vNum = parseInt(match[1])
          const date = match[2]
          return (
            <button
              key={`cite-${i}`}
              onClick={() => onCiteVersion?.(vNum)}
              className="inline-flex items-center gap-1 px-2 py-0.5 mx-0.5 rounded-full text-xs font-medium bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 hover:bg-primary-200 dark:hover:bg-primary-900/50 transition-colors cursor-pointer border border-primary-200 dark:border-primary-800"
              title={`Version ${vNum} · ${date}`}
            >
              <GitCommit className="h-3 w-3" />
              <span>v{vNum}</span>
              <span className="text-[10px] opacity-70">·</span>
              <span className="text-[10px]">{date}</span>
              <ExternalLink className="h-2.5 w-2.5 opacity-50" />
            </button>
          )
        }
        return <span key={`text-${i}`}>{part}</span>
      })}
    </div>
  )
}

export function ChatUI({ patientId, className, initialMessage, onCiteVersion }: ChatUIProps) {
  const [messages, setMessages] = useState<Message[]>(() => {
    if (initialMessage) {
      return [{
        id: 'initial',
        role: 'assistant',
        content: initialMessage,
        timestamp: new Date(),
      }]
    }
    return [{
      id: 'welcome',
      role: 'assistant',
      content: "Hello! I'm your AI clinical assistant. How can I help you today? Select a patient to ask about their records, or ask me about available commands.",
      timestamp: new Date(),
    }]
  })
  const [input, setInput] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const { isStreaming, error, sendMessage, cancel } = useSSE({
    onToken: (text) => {
      setMessages(prev => {
        const updated = [...prev]
        const lastMsg = updated[updated.length - 1]
        if (lastMsg?.isStreaming) {
          updated[updated.length - 1] = {
            ...lastMsg,
            content: text,
          }
        }
        return updated
      })
    },
    onTrace: (message) => {
      setMessages(prev => {
        const updated = [...prev]
        const lastMsg = updated[updated.length - 1]
        if (lastMsg?.isStreaming) {
          updated[updated.length - 1] = {
            ...lastMsg,
            trace: [...(lastMsg.trace || []), message],
          }
        }
        return updated
      })
    },
    onDone: (responseText, traceEvents) => {
      setMessages(prev => {
        const updated = [...prev]
        const lastMsg = updated[updated.length - 1]
        if (lastMsg?.isStreaming) {
          updated[updated.length - 1] = {
            ...lastMsg,
            content: responseText,
            trace: traceEvents,
            isStreaming: false,
          }
        }
        return updated
      })
    },
  })

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSend = useCallback(() => {
    const text = input.trim()
    if (!text || isStreaming) return

    setInput('')
    setShowSuggestions(false)

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date(),
    }

    const assistantMsg: Message = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
      trace: [],
      citations: [],
    }

    setMessages(prev => [...prev, userMsg, assistantMsg])

    sendMessage(text, {
      patient_id: patientId,
    })
  }, [input, isStreaming, patientId, sendMessage])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleMicClick = useCallback(() => {
    setInput(prev => prev + (prev ? ' ' : '') + '[Voice input coming in Week 10]')
  }, [])

  const handleSuggestionClick = useCallback((suggestion: string) => {
    setInput(suggestion)
    setShowSuggestions(false)
    setTimeout(() => inputRef.current?.focus(), 100)
  }, [])

  const suggestions = [
    'What can you help me with?',
    'Show me patient commands',
    'How does the version system work?',
  ]

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className={cn(
                'flex gap-3 max-w-3xl',
                msg.role === 'user' ? 'ml-auto' : 'mr-auto'
              )}
            >
              {/* Avatar */}
              <div
                className={cn(
                  'flex h-8 w-8 shrink-0 items-center justify-center rounded-full mt-0.5',
                  msg.role === 'user'
                    ? 'bg-primary-100 dark:bg-primary-900/30'
                    : 'bg-gray-100 dark:bg-gray-800'
                )}
              >
                {msg.role === 'user' ? (
                  <User className="h-4 w-4 text-primary-600 dark:text-primary-400" />
                ) : (
                  <Bot className="h-4 w-4 text-gray-600 dark:text-gray-400" />
                )}
              </div>

              {/* Message Content */}
              <div className={cn('flex-1 min-w-0')}>
                <div
                  className={cn(
                    'rounded-xl px-4 py-3 text-sm leading-relaxed',
                    msg.role === 'user'
                      ? 'bg-primary-600 text-white'
                      : 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-white'
                  )}
                >
                  {msg.isStreaming && !msg.content ? (
                    <div className="flex items-center gap-2 text-gray-500">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>Thinking...</span>
                    </div>
                  ) : msg.role === 'assistant' ? (
                    renderContentWithCitations(msg.content, msg.citations, onCiteVersion)
                  ) : (
                    <p>{msg.content}</p>
                  )}
                </div>

                {/* Citations bar */}
                {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && !msg.isStreaming && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {msg.citations.slice(0, 4).map((cite, i) => (
                      <button
                        key={`cite-${i}`}
                        onClick={() => onCiteVersion?.(cite.version_number)}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 border border-primary-200 dark:border-primary-800 hover:bg-primary-100 dark:hover:bg-primary-900/30 transition-colors"
                      >
                        <GitCommit className="h-2.5 w-2.5" />
                        <span>v{cite.version_number}</span>
                        <span className="text-gray-400">·</span>
                        <span>{cite.date || 'recent'}</span>
                      </button>
                    ))}
                    {msg.citations.length > 4 && (
                      <span className="text-[10px] text-gray-400 self-center">
                        +{msg.citations.length - 4} more
                      </span>
                    )}
                  </div>
                )}

                {/* Agent Trace */}
                {msg.role === 'assistant' && msg.trace && msg.trace.length > 0 && (
                  <AgentTrace
                    events={msg.trace}
                    isStreaming={!!msg.isStreaming}
                    onFinished={!msg.isStreaming}
                  />
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Error Message */}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-300 max-w-3xl"
          >
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </motion.div>
        )}

        {/* Suggestions */}
        {showSuggestions && messages.length <= 2 && (
          <div className="flex flex-wrap gap-2 max-w-3xl">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => handleSuggestionClick(s)}
                className="text-xs px-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-white transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="border-t border-gray-200 dark:border-gray-700 px-4 py-3 bg-white dark:bg-gray-900">
        <div className="flex items-end gap-2 max-w-3xl mx-auto">
          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about a patient, schedule, or documents..."
              rows={1}
              disabled={isStreaming}
              className={cn(
                'w-full resize-none rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-4 py-3 pr-10 text-sm text-gray-900 dark:text-white placeholder-gray-400',
                'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
              onInput={(e) => {
                const target = e.currentTarget
                target.style.height = 'auto'
                target.style.height = Math.min(target.scrollHeight, 200) + 'px'
              }}
            />
            {!input && !isStreaming && (
              <button
                onClick={handleMicClick}
                className="absolute right-3 bottom-2.5 text-gray-400 hover:text-red-500 transition-colors"
                aria-label="Voice input"
                title="Voice input (coming Week 10)"
              >
                <Mic className="h-4 w-4" />
              </button>
            )}
          </div>

          <div className="flex items-center gap-1">
            {isStreaming ? (
              <Button
                onClick={cancel}
                variant="destructive"
                size="icon"
                className="h-10 w-10 rounded-xl"
                aria-label="Stop generating"
              >
                <Square className="h-4 w-4" />
              </Button>
            ) : (
              <Button
                onClick={handleSend}
                disabled={!input.trim()}
                size="icon"
                className="h-10 w-10 rounded-xl"
                aria-label="Send message"
              >
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>

        {isStreaming && (
          <div className="flex items-center gap-1.5 mt-2 max-w-3xl mx-auto">
            <Sparkles className="h-3 w-3 text-primary-500 animate-pulse" />
            <span className="text-[10px] text-gray-400">AI is generating response...</span>
          </div>
        )}

        {!isStreaming && (
          <p className="text-[10px] text-gray-400 mt-2 max-w-3xl mx-auto">
            AI responses are suggestions — requires doctor validation. Shift+Enter for new line.
          </p>
        )}
      </div>
    </div>
  )
}
