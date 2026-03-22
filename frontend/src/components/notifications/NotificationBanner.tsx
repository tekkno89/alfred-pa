import { useMemo, useState } from 'react'
import { X, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useNotificationContext } from './NotificationProvider'

export function NotificationBanner() {
  const { notifications, dismissBypassAlert } = useNotificationContext()
  const [dismissed, setDismissed] = useState(false)

  // Derive alert state directly from notifications (no useEffect)
  const alert = useMemo(() => {
    if (dismissed) return null
    const alertNotifications = notifications.filter(
      (n) => n.type === 'focus_bypass' || n.type === 'triage.urgent'
    )
    if (alertNotifications.length === 0) return null
    const latest = alertNotifications[alertNotifications.length - 1]
    if (latest.type === 'triage.urgent') {
      const abstract = (latest as Record<string, unknown>).abstract as string | undefined
      const sender = (latest as Record<string, unknown>).sender_name as string | undefined
      return {
        message: abstract || 'An urgent message needs your attention',
        senderName: sender || null,
      }
    }
    return {
      message: latest.message || 'Someone is trying to reach you urgently!',
      senderName: latest.sender_name || null,
    }
  }, [notifications, dismissed])

  // Reset dismissed when new alerts come in
  const alertCount = notifications.filter(
    (n) => n.type === 'focus_bypass' || n.type === 'triage.urgent'
  ).length
  // Using a ref-like pattern: if alert count increases after dismissal, un-dismiss
  const [lastDismissedCount, setLastDismissedCount] = useState(0)
  if (dismissed && alertCount > lastDismissedCount) {
    setDismissed(false)
  }

  const handleDismiss = () => {
    setDismissed(true)
    setLastDismissedCount(alertCount)
    dismissBypassAlert()
  }

  if (!alert) return null

  return (
    <div className="fixed top-0 left-0 right-0 z-[100] bg-red-600 text-white p-4 flex items-center justify-between animate-pulse-subtle">
      <div className="flex items-center gap-3">
        <AlertTriangle className="h-5 w-5 shrink-0 animate-bounce" />
        <div>
          <span className="font-medium">{alert.message}</span>
          {alert.senderName && (
            <p className="text-sm text-red-100">From: {alert.senderName}</p>
          )}
        </div>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={handleDismiss}
        className="text-white hover:bg-red-700 shrink-0"
      >
        <X className="h-4 w-4" />
      </Button>
      <style>{`
        @keyframes pulse-subtle {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.85; }
        }
        .animate-pulse-subtle {
          animation: pulse-subtle 2s ease-in-out infinite;
        }
      `}</style>
    </div>
  )
}
