'use client'

import { useState, useRef, useCallback } from 'react'

export interface SSEEvent {
  type: 'trace' | 'token' | 'done' | 'error'
  data: Record<string, unknown>
}

export interface SSEState {
  isConnected: boolean
  isStreaming: boolean
  trace: string[]
  response: string
  error: string | null
  tookMs: number
}

interface UseSSEOptions {
  onToken?: (text: string) => void
  onTrace?: (message: string) => void
  onDone?: (response: string, trace: string[]) => void
  onError?: (message: string) => void
}

/**
 * Hook to consume SSE streams from the agent chat endpoint.
 *
 * Usage:
 *   const { sendMessage, isStreaming, response, trace } = useSSE()
 *   sendMessage("What is Priya's BP trend?", { patient_id: "..." })
 */
export function useSSE(options?: UseSSEOptions) {
  const [state, setState] = useState<SSEState>({
    isConnected: false,
    isStreaming: false,
    trace: [],
    response: '',
    error: null,
    tookMs: 0,
  })

  const abortRef = useRef<AbortController | null>(null)

  const reset = useCallback(() => {
    setState({
      isConnected: false,
      isStreaming: false,
      trace: [],
      response: '',
      error: null,
      tookMs: 0,
    })
  }, [])

  const sendMessage = useCallback(
    async (query: string, opts?: { patient_id?: string; conversation_id?: string }) => {
      // Abort any previous connection
      if (abortRef.current) {
        abortRef.current.abort()
      }
      reset()

      const controller = new AbortController()
      abortRef.current = controller

      setState(prev => ({ ...prev, isConnected: true, isStreaming: true }))

      try {
        const response = await fetch('/api/v1/agent/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
          },
          body: JSON.stringify({
            query,
            patient_id: opts?.patient_id,
            conversation_id: opts?.conversation_id,
          }),
          signal: controller.signal,
        })

        if (!response.ok) {
          const errorBody = await response.text()
          throw new Error(`Server error ${response.status}: ${errorBody}`)
        }

        const reader = response.body?.getReader()
        if (!reader) {
          throw new Error('Response body is not readable')
        }

        const decoder = new TextDecoder()
        let buffer = ''
        let currentResponse = ''
        let currentTrace: string[] = []

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })

          // Parse SSE events from buffer
          const lines = buffer.split('\n')
          buffer = lines.pop() || '' // keep incomplete line

          let eventType = ''
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              const dataStr = line.slice(6)
              try {
                const data = JSON.parse(dataStr)

                if (eventType === 'trace') {
                  currentTrace = [...currentTrace, data.message]
                  setState(prev => ({ ...prev, trace: currentTrace }))
                  options?.onTrace?.(data.message)
                } else if (eventType === 'token') {
                  currentResponse += data.text
                  setState(prev => ({ ...prev, response: currentResponse }))
                  options?.onToken?.(data.text)
                } else if (eventType === 'done') {
                  currentResponse = data.response || currentResponse
                  currentTrace = data.trace_events || currentTrace
                  setState(prev => ({
                    ...prev,
                    isStreaming: false,
                    response: currentResponse,
                    trace: currentTrace,
                    tookMs: data.took_ms || 0,
                  }))
                  options?.onDone?.(data.response, data.trace_events)
                } else if (eventType === 'error') {
                  setState(prev => ({
                    ...prev,
                    isStreaming: false,
                    error: data.message,
                  }))
                  options?.onError?.(data.message)
                }
              } catch {
                // Skip unparseable data
              }
              eventType = ''
            }
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return
        const message = err instanceof Error ? err.message : 'Unknown error'
        setState(prev => ({ ...prev, isStreaming: false, error: message }))
        options?.onError?.(message)
      } finally {
        setState(prev => ({ ...prev, isConnected: false }))
      }
    },
    [reset, options]
  )

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    setState(prev => ({ ...prev, isConnected: false, isStreaming: false }))
  }, [])

  return {
    ...state,
    sendMessage,
    cancel,
    reset,
  }
}
