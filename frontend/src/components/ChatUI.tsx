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
} from 'lucide-react'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  isStreaming?: boolean
  trace?: string[]
}

interface ChatUIProps {
  patientId?: string
  className?: string
  initialMessage?: string
}

export function ChatUI({ patientId, className, initialMessage }: ChatUIProps) {
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

    // Add user message
    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date(),
    }

    // Add placeholder assistant message
    const assistantMsg: Message = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
      trace: [],
    }

    setMessages(prev => [...prev, userMsg, assistantMsg])

    // Send to SSE endpoint
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
    // Voice input placeholder — will be implemented in Week 10/11
    setInput(prev => prev + (prev ? ' ' : '') + '[🎤 Voice input coming in Week 10]')
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
                    <div className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap">
                      {msg.content}
                    </div>
                  ) : (
                    <p>{msg.content}</p>
                  )}
                </div>

                {/* Agent Trace (for assistant messages) */}
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

        {/* Streaming indicator */}
        {isStreaming && (
          <div className="flex items-center gap-1.5 mt-2 max-w-3xl mx-auto">
            <Sparkles className="h-3 w-3 text-primary-500 animate-pulse" />
            <span className="text-[10px] text-gray-400">AI is generating response...</span>
          </div>
        )}

        {/* Footer hint */}
        {!isStreaming && (
          <p className="text-[10px] text-gray-400 mt-2 max-w-3xl mx-auto">
            AI responses are suggestions — requires doctor validation. Shift+Enter for new line.
          </p>
        )}
      </div>
    </div>
  )
}
