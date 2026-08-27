import { useEffect, useRef, useState, useCallback } from 'react'

export interface WebSocketEvent {
  type: string
  data: any
}

function useRealtimeSocket(role: 'patient' | 'doctor', id: string | null) {
  const wsRef = useRef<WebSocket | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState<WebSocketEvent | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reconnectAttempts = useRef(0)
  const maxReconnectAttempts = 5
  const tag = role === 'patient' ? '[PatientWS]' : '[DoctorWS]'

  const clearPing = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current)
      pingIntervalRef.current = null
    }
  }, [])

  const connect = useCallback(() => {
    if (!id) return
    const current = wsRef.current
    // Skip while a socket is already OPEN *or still CONNECTING* — without the
    // CONNECTING check, React StrictMode's effect double-mount (mount → cleanup
    // → mount) could race a second connect() in before the first socket settles.
    if (current && (current.readyState === WebSocket.OPEN || current.readyState === WebSocket.CONNECTING)) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/${role}/${id}`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      // Set by disconnect() before it closes a socket that is still CONNECTING.
      // Chrome fires `error` when a connecting socket is aborted; React
      // StrictMode's cleanup does exactly that, and without this flag every
      // page load logged "[DoctorWS] Error: Event" to the console.
      let intentionallyClosed = false

      ws.onopen = () => {
        console.log(`${tag} Connected`)
        setIsConnected(true)
        reconnectAttempts.current = 0
        clearPing()
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }))
          }
        }, 30000)
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'pong') return
          setLastEvent(data)
        } catch (e) {
          console.error(`${tag} Failed to parse message:`, e)
        }
      }

      ws.onclose = () => {
        console.log(`${tag} Disconnected`)
        setIsConnected(false)
        if (wsRef.current === ws) wsRef.current = null
        clearPing()
        if (intentionallyClosed) return
        if (reconnectAttempts.current < maxReconnectAttempts) {
          const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 30000)
          reconnectAttempts.current++
          reconnectTimeoutRef.current = setTimeout(connect, delay)
        }
      }

      ws.onerror = (error) => {
        if (intentionallyClosed) return
        console.error(`${tag} Error:`, error)
      }
    } catch (e) {
      console.error(`${tag} Failed to create WebSocket:`, e)
    }
  }, [role, id, tag, clearPing])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    clearPing()
    const ws = wsRef.current
    if (ws) {
      // Detach handlers BEFORE close() so an abort of a still-CONNECTING
      // socket (React StrictMode effect-cleanup) can't fire onerror / onclose
      // and can't schedule a reconnect.
      ws.onopen = ws.onmessage = ws.onclose = ws.onerror = null
      try { ws.close() } catch { /* already closed */ }
      wsRef.current = null
    }
    setIsConnected(false)
  }, [clearPing])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return { isConnected, lastEvent, connect, disconnect }
}

export function usePatientWebSocket(patientId: string | null) {
  return useRealtimeSocket('patient', patientId)
}

export function useDoctorWebSocket(doctorId: string | null) {
  return useRealtimeSocket('doctor', doctorId)
}