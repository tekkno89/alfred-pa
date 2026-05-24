import { Users, Hash } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useTransparency } from '@/hooks/useTriageTransparency'
import type { SenderPatternData } from '@/types'

const ACTION_COLORS: Record<string, string> = {
  notify_now: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
  summarize_next: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  summarize_eod: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
  ignore: 'bg-gray-100 text-gray-800 dark:bg-gray-900/40 dark:text-gray-200',
}

const ACTION_LABELS: Record<string, string> = {
  notify_now: 'Immediate',
  summarize_next: 'Next Break',
  summarize_eod: 'EOD',
  ignore: 'Ignored',
}

function PatternItem({ pattern }: { pattern: SenderPatternData }) {
  const topActions = Object.entries(pattern.action_distribution)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 3)

  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-muted/50">
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex items-center gap-1">
          <Users className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium truncate">{pattern.sender_name}</span>
        </div>
        <div className="flex items-center gap-1 text-muted-foreground">
          <Hash className="h-3 w-3" />
          <span className="text-sm truncate">{pattern.channel_name}</span>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <div className="flex gap-1">
          {topActions.map(([action, percent]) => (
            <Badge key={action} variant="outline" className={`text-xs ${ACTION_COLORS[action] ?? ''}`}>
              {ACTION_LABELS[action] ?? action}: {(percent * 100).toFixed(0)}%
            </Badge>
          ))}
        </div>
        <Badge variant="secondary" className="text-xs">
          n={pattern.sample_count}
        </Badge>
      </div>
    </div>
  )
}

export function SenderPatternsCard() {
  const { data, isLoading, error } = useTransparency()

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          Loading sender patterns...
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-destructive">
          Failed to load sender patterns. Please try again.
        </CardContent>
      </Card>
    )
  }

  const patterns = data?.sender_patterns ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sender Patterns</CardTitle>
        <CardDescription>
          How messages from different senders are typically handled based on your feedback.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {patterns.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">
            No sender patterns yet. Patterns emerge as you provide feedback on message handling.
          </p>
        ) : (
          <div className="space-y-1 border rounded-lg divide-y">
            {patterns.map((pattern, idx) => (
              <PatternItem key={`${pattern.sender_slack_id}-${pattern.channel_name}-${idx}`} pattern={pattern} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
