import { useEffect, useState } from 'react'
import { X, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useNotificationContext } from './NotificationProvider'

export function NotificationBanner() {
  const { notifications, clearNotifications } = useNotificationContext()
  const [visible, setVisible] = useState(false)
  const [message, setMessage] = useState('')

  // Show banner when there's a new focus_bypass notification
  useEffect(() => {
    const bypassNotifications = notifications.filter((n) => n.type === 'focus_bypass')
    if (bypassNotifications.length > 0) {
      const latest = bypassNotifications[bypassNotifications.length - 1]
      setMessage(latest.message || 'Someone is trying to reach you urgently!')
      setVisible(true)
    }
  }, [notifications])

  const handleDismiss = () => {
    setVisible(false)
    clearNotifications()
  }

  if (!visible) return null

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-red-600 text-white p-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <AlertTriangle className="h-5 w-5" />
        <span className="font-medium">{message}</span>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={handleDismiss}
        className="text-white hover:bg-red-700"
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  )
}
