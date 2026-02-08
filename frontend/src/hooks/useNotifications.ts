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

    // EventSource doesn't support custom headers, so we need to use a different approach
    // Use fetch with streaming instead
    const controller = new AbortController()

    fetch(`${API_BASE_URL}/notifications/subscribe`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'text/event-stream',
      },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error('Failed to connect to notifications')
        }

        setIsConnected(true)
        const reader = response.body?.getReader()
        if (!reader) return

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const event: NotificationEvent = JSON.parse(line.slice(6))
                setLastEvent(event)
                handlersRef.current.forEach((handler) => handler(event))
              } catch {
                // Skip invalid JSON
              }
            }
          }
        }
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          console.error('Notification stream error:', error)
          setIsConnected(false)
        }
      })

    // Store abort controller for cleanup
    eventSourceRef.current = { close: () => controller.abort() } as EventSource
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
