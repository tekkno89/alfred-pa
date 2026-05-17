import { useState } from 'react'
import { Plane, Loader2 } from 'lucide-react'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  useTriageSettings,
  useToggleAwayMode,
  useConfigureAwayMode,
} from '@/hooks/useTriage'

interface AwayModeToggleProps {
  showLabel?: boolean
}

export function AwayModeToggle({ showLabel = true }: AwayModeToggleProps) {
  const { data: settings, isLoading } = useTriageSettings()
  const toggleMutation = useToggleAwayMode()
  const configureMutation = useConfigureAwayMode()

  const isEnabled = settings?.away_mode_enabled ?? false
  const notifyBehavior = settings?.away_mode_notify_now_behavior ?? 'queue_for_catchup'
  const isPending = toggleMutation.isPending || configureMutation.isPending

  const [localNotifyBehavior, setLocalNotifyBehavior] = useState<string | null>(null)

  const handleToggle = async (checked: boolean) => {
    await toggleMutation.mutateAsync({ enabled: checked })
  }

  const handleNotifyBehaviorChange = async (value: 'push_immediately' | 'queue_for_catchup') => {
    setLocalNotifyBehavior(value)
    await configureMutation.mutateAsync({ notify_now_behavior: value })
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin" />
        {showLabel && <span className="text-sm text-muted-foreground">Loading...</span>}
      </div>
    )
  }

  const currentNotifyBehavior = localNotifyBehavior ?? notifyBehavior

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Plane className="h-4 w-4 text-sky-600" />
          <Label htmlFor="away-mode-toggle" className="font-medium">
            Away Mode
          </Label>
        </div>
        <Switch
          id="away-mode-toggle"
          checked={isEnabled}
          onCheckedChange={handleToggle}
          disabled={isPending}
        />
      </div>

      {isEnabled && (
        <div className="space-y-2 pl-6">
          <p className="text-sm text-muted-foreground">
            You're marked as away. Non-urgent messages will be queued.
          </p>
          <div className="flex items-center gap-2">
            <Label htmlFor="notify-behavior" className="text-sm">
              Notify Now behavior:
            </Label>
            <Select
              value={currentNotifyBehavior}
              onValueChange={handleNotifyBehaviorChange}
              disabled={isPending}
            >
              <SelectTrigger id="notify-behavior" className="w-48">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="push_immediately">Push immediately</SelectItem>
                <SelectItem value="queue_for_catchup">Queue for catch-up</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      )}
    </div>
  )
}
