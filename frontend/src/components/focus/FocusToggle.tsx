import { useState } from 'react'
import { Bell, BellOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  useFocusStatus,
  useEnableFocus,
  useDisableFocus,
} from '@/hooks/useFocusMode'

interface FocusToggleProps {
  size?: 'sm' | 'default' | 'lg'
  showLabel?: boolean
}

export function FocusToggle({ size = 'default', showLabel = true }: FocusToggleProps) {
  const { data: status, isLoading } = useFocusStatus()
  const enableMutation = useEnableFocus()
  const disableMutation = useDisableFocus()
  const [durationMinutes, setDurationMinutes] = useState<number | undefined>()

  const isActive = status?.is_active ?? false
  const isPending = enableMutation.isPending || disableMutation.isPending

  const handleToggle = async () => {
    if (isActive) {
      await disableMutation.mutateAsync()
    } else {
      await enableMutation.mutateAsync({ duration_minutes: durationMinutes })
    }
  }

  if (isLoading) {
    return (
      <Button variant="outline" size={size} disabled>
        Loading...
      </Button>
    )
  }

  return (
    <Button
      variant={isActive ? 'destructive' : 'default'}
      size={size}
      onClick={handleToggle}
      disabled={isPending}
    >
      {isActive ? (
        <>
          <BellOff className="h-4 w-4 mr-2" />
          {showLabel && (isPending ? 'Disabling...' : 'End Focus')}
        </>
      ) : (
        <>
          <Bell className="h-4 w-4 mr-2" />
          {showLabel && (isPending ? 'Enabling...' : 'Start Focus')}
        </>
      )}
    </Button>
  )
}
