import { createContext, useContext, useEffect, useCallback, useState, ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet } from '@/lib/api'
import { useNotifications } from '@/hooks/useNotifications'
import { useAlertSound } from '@/hooks/useAlertSound'
import { useTitleFlash } from '@/hooks/useTitleFlash'
import type { NotificationEvent, FocusSettingsResponse, BypassNotificationConfig } from '@/types'

const SOUND_LOOP_INTERVAL_MS = 5000

const FOCUS_EVENT_TYPES = [
  'focus_started',
  'focus_ended',
  'pomodoro_work_started',
  'pomodoro_break_started',
  'pomodoro_complete',
]

interface NotificationContextValue {
  isConnected: boolean
  lastEvent: NotificationEvent | null
  notifications: NotificationEvent[]
  clearNotifications: () => void
  dismissBypassAlert: () => void
}

const NotificationContext = createContext<NotificationContextValue | null>(null)

export function useNotificationContext() {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error('useNotificationContext must be used within NotificationProvider')
  }
  return context
}

const DEFAULT_CONFIG: BypassNotificationConfig = {
  alfred_ui_enabled: true,
  email_enabled: false,
  email_address: null,
  sms_enabled: false,
  phone_number: null,
  alert_sound_enabled: true,
  alert_sound_name: 'chime',
  alert_title_flash_enabled: true,
}

interface NotificationProviderProps {
  children: ReactNode
}

export function NotificationProvider({ children }: NotificationProviderProps) {
  const [notifications, setNotifications] = useState<NotificationEvent[]>([])
  // When non-null, the sound loop effect plays this sound repeatedly
  const [loopingSound, setLoopingSound] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const { playAlertSound } = useAlertSound()
  const { startTitleFlash, stopTitleFlash } = useTitleFlash()

  // Eagerly fetch focus settings so bypass config is always cached
  useQuery({
    queryKey: ['focus-settings'],
    queryFn: () => apiGet<FocusSettingsResponse>('/focus/settings'),
    staleTime: 5 * 60 * 1000,
  })

  // Sound loop driven by React state — plays immediately, then every 5s
  useEffect(() => {
    if (!loopingSound) return

    playAlertSound(loopingSound)
    const id = setInterval(() => {
      playAlertSound(loopingSound)
    }, SOUND_LOOP_INTERVAL_MS)

    return () => clearInterval(id)
  }, [loopingSound, playAlertSound])

  const dismissBypassAlert = useCallback(() => {
    setLoopingSound(null)
    stopTitleFlash()
    setNotifications([])
  }, [stopTitleFlash])

  const handleNotification = useCallback((event: NotificationEvent) => {
    // Skip keepalive and connected events
    if (event.type === 'connected') return

    setNotifications((prev) => [...prev, event])

    // Invalidate focus status cache on any focus-related event so the UI
    // updates immediately (e.g. when focus is toggled via the LLM tool)
    if (FOCUS_EVENT_TYPES.includes(event.type)) {
      queryClient.invalidateQueries({ queryKey: ['focus-status'] })
    }

    // Invalidate todo queries when todos change (e.g. via Slack or LLM tool)
    if (event.type === 'todos_changed') {
      queryClient.invalidateQueries({ queryKey: ['todos'] })
    }

    // Invalidate calendar queries when events change (webhook, agent tool, or API)
    if (event.type === 'calendar_changed') {
      queryClient.invalidateQueries({ queryKey: ['calendar', 'events'] })
    }

    // Stop alerts when focus mode ends
    if (event.type === 'focus_ended') {
      setLoopingSound(null)
      stopTitleFlash()
      return
    }

    // Triage urgent notification — looping alert + banner (same as bypass)
    if (event.type === 'triage.urgent') {
      setLoopingSound('urgent')
      startTitleFlash('URGENT MESSAGE')

      // Show browser notification
      if ('Notification' in window && Notification.permission === 'granted') {
        const abstract = (event as Record<string, unknown>).abstract as string | undefined
        new Notification('Urgent Triage Message', {
          body: abstract || 'An urgent message needs your attention',
          icon: '/favicon.ico',
        })
      }

      // Invalidate triage queries
      queryClient.invalidateQueries({ queryKey: ['triage-classifications'] })
      queryClient.invalidateQueries({ queryKey: ['triage-session-stats'] })
    }

    // Triage break notification
    if (event.type === 'triage.break_check_slack') {
      queryClient.invalidateQueries({ queryKey: ['triage-classifications'] })
    }

    // Triage break notification clear
    if (event.type === 'triage.break_notification_clear') {
      // Clear triage-related notifications from the list
      setNotifications((prev) =>
        prev.filter((n) => n.type !== 'triage.break_check_slack')
      )
    }

    // Enhanced handling for bypass events
    if (event.type === 'focus_bypass') {
      // Read user's notification config from cache
      const settings = queryClient.getQueryData<FocusSettingsResponse>(['focus-settings'])
      const config = settings?.bypass_notification_config ?? DEFAULT_CONFIG

      // Start looping alert sound if enabled
      if (config.alert_sound_enabled) {
        setLoopingSound(config.alert_sound_name)
      }

      // Flash title if enabled
      if (config.alert_title_flash_enabled) {
        startTitleFlash('URGENT MESSAGE')
      }

      // Show browser notification
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('Urgent Message', {
          body: event.message || 'Someone is trying to reach you urgently!',
          icon: '/favicon.ico',
        })
      }
    }
  }, [queryClient, startTitleFlash, stopTitleFlash])

  const { isConnected, lastEvent } = useNotifications(handleNotification)

  const clearNotifications = useCallback(() => {
    setNotifications([])
  }, [])

  // Request notification permission on mount
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }
  }, [])

  return (
    <NotificationContext.Provider
      value={{ isConnected, lastEvent, notifications, clearNotifications, dismissBypassAlert }}
    >
      {children}
    </NotificationContext.Provider>
  )
}
