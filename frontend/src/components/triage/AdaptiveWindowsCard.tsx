import { useState } from 'react'
import { Clock, RotateCcw, Loader2 } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  useAdaptiveWindows,
  useResetAdaptiveWindow,
} from '@/hooks/useTriage'
import type { AdaptiveWindow } from '@/types'

function formatWindow(minutes: number): string {
  if (minutes < 60) {
    return `${minutes}m`
  } else if (minutes < 1440) {
    const hours = Math.round(minutes / 60)
    return `${hours}h`
  } else {
    return '1d'
  }
}

function WindowRow({
  window,
  onReset,
  resetting,
}: {
  window: AdaptiveWindow
  onReset: () => void
  resetting: boolean
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border last:border-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{window.message_type_name}</div>
        <div className="text-xs text-muted-foreground flex items-center gap-2">
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {formatWindow(window.window_minutes)}
          </span>
          {window.is_learning ? (
            <span className="text-yellow-600 dark:text-yellow-400">Learning...</span>
          ) : (
            <span>{window.sample_count} samples</span>
          )}
        </div>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={(e) => {
          e.stopPropagation()
          onReset()
        }}
        disabled={resetting}
        className="shrink-0"
      >
        {resetting ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <RotateCcw className="h-4 w-4" />
        )}
      </Button>
    </div>
  )
}

export function AdaptiveWindowsCard() {
  const { data, isLoading } = useAdaptiveWindows()
  const resetMutation = useResetAdaptiveWindow()
  const [resettingType, setResettingType] = useState<string | null>(null)

  const handleReset = async (messageTypeName: string) => {
    setResettingType(messageTypeName)
    try {
      await resetMutation.mutateAsync(messageTypeName)
    } finally {
      setResettingType(null)
    }
  }

  if (isLoading) {
    return (
      <Card className="hover:shadow-md transition-shadow h-full flex flex-col">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Clock className="h-4 w-4" />
            Delivery Windows
          </CardTitle>
        </CardHeader>
        <CardContent className="flex-1">
          <p className="text-sm text-muted-foreground">Loading...</p>
        </CardContent>
      </Card>
    )
  }

  const windows = data?.windows ?? []

  return (
    <Card className="hover:shadow-md transition-shadow h-full flex flex-col">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Clock className="h-4 w-4" />
          Delivery Windows
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Learned response times per message type
        </p>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto max-h-80">
        {windows.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No delivery windows configured yet. Windows are learned as you interact with messages.
          </p>
        ) : (
          <div className="divide-y divide-border">
            {windows.map((window) => (
              <WindowRow
                key={window.message_type_name}
                window={window}
                onReset={() => handleReset(window.message_type_name)}
                resetting={resettingType === window.message_type_name}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
