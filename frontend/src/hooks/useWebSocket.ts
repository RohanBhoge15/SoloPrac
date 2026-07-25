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
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/${role}/${id}`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

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
        wsRef.current = null
        clearPing()
        if (reconnectAttempts.current < maxReconnectAttempts) {
          const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 30000)
          reconnectAttempts.current++
          reconnectTimeoutRef.current = setTimeout(connect, delay)
        }
      }

      ws.onerror = (error) => {
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
    if (wsRef.current) {
      wsRef.current.close()
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