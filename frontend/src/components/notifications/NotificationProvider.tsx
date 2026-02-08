import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { useNotifications } from '@/hooks/useNotifications'
import type { NotificationEvent } from '@/types'

interface NotificationContextValue {
  isConnected: boolean
  lastEvent: NotificationEvent | null
  notifications: NotificationEvent[]
  clearNotifications: () => void
}

const NotificationContext = createContext<NotificationContextValue | null>(null)

export function useNotificationContext() {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotificationContext must be used within NotificationProvider')
  }
  return context
}

interface NotificationProviderProps {
  children: ReactNode
}

export function NotificationProvider({ children }: NotificationProviderProps) {
  const [notifications, setNotifications] = useState<NotificationEvent[]>([])

  const handleNotification = (event: NotificationEvent) => {
    // Skip keepalive and connected events
    if (event.type === 'connected') return

    setNotifications((prev) => [...prev, event])

    // Show browser notification for bypass events
    if (event.type === 'focus_bypass' && 'Notification' in window) {
      if (Notification.permission === 'granted') {
        new Notification('Urgent Message', {
          body: event.message || 'Someone is trying to reach you urgently!',
          icon: '/favicon.ico',
        })
      }
    }
  }

  const { isConnected, lastEvent } = useNotifications(handleNotification)

  const clearNotifications = () => {
    setNotifications([])
  }

  // Request notification permission on mount
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }
  }, [])

  return (
    <NotificationContext.Provider
      value={{ isConnected, lastEvent, notifications, clearNotifications }}
    >
      {children}
    </NotificationContext.Provider>
  )
}
