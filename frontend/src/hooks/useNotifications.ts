import { useEffect, useCallback, useRef, useState } from 'react'
import { useAuthStore } from '@/lib/auth'
import type { NotificationEvent } from '@/types'

const API_BASE_URL =
  (import.meta.env.VITE_API_URL || 'http://localhost:8000') + '/api'

type NotificationHandler = (event: NotificationEvent) => void

export function useNotifications(onNotification?: NotificationHandler) {
  const token = useAuthStore((state) => state.token)
  const [isConnected, setIsConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState<NotificationEvent | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const handlersRef = useRef<Set<NotificationHandler>>(new Set())

  // Add handler to ref
  useEffect(() => {
    if (onNotification) {
      handlersRef.current.add(onNotification)
      return () => {
        handlersRef.current.delete(onNotification)
      }
    }
  }, [onNotification])

  const connect = useCallback(() => {
    if (!token || eventSourceRef.current) return

    const url = `${API_BASE_URL}/notifications/subscribe?token=${encodeURIComponent(token)}`
    const es = new EventSource(url)

    es.onopen = () => {
      setIsConnected(true)
    }

    es.onmessage = (e) => {
      try {
        const event: NotificationEvent = JSON.parse(e.data)
        setLastEvent(event)
        handlersRef.current.forEach((handler) => handler(event))
      } catch {
        // Skip invalid JSON
      }
    }

    es.onerror = () => {
      // EventSource auto-reconnects; update connected state
      if (es.readyState === EventSource.CLOSED) {
        setIsConnected(false)
        eventSourceRef.current = null
      } else {
        // CONNECTING state — auto-reconnecting
        setIsConnected(false)
      }
    }

    eventSourceRef.current = es
  }, [token])

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
      setIsConnected(false)
    }
  }, [])

  useEffect(() => {
    connect()
    return disconnect
  }, [connect, disconnect])

  return {
    isConnected,
    lastEvent,
    connect,
    disconnect,
  }
}
