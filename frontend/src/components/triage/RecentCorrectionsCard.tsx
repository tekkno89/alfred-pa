import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useTransparency } from '@/hooks/useTriageTransparency'
import type { CorrectionData } from '@/types'

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

function CorrectionItem({ correction }: { correction: CorrectionData }) {
  const date = new Date(correction.created_at)
  const timeAgo = getTimeAgo(date)

  return (
    <div className="flex items-start justify-between py-2 px-3 rounded-lg hover:bg-muted/50">
      <div className="flex-1 min-w-0 mr-3">
        <p className="text-sm truncate">{correction.message_text}</p>
        <p className="text-xs text-muted-foreground mt-1">{timeAgo}</p>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <Badge variant="outline" className={`text-xs ${ACTION_COLORS[correction.corrected_action] ?? ''}`}>
          {ACTION_LABELS[correction.corrected_action] ?? correction.corrected_action}
        </Badge>
      </div>
    </div>
  )
}

function getTimeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000)
  
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`
  
  return date.toLocaleDateString()
}

export function RecentCorrectionsCard() {
  const { data, isLoading, error } = useTransparency()

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          Loading corrections...
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-destructive">
          Failed to load corrections. Please try again.
        </CardContent>
      </Card>
    )
  }

  const corrections = data?.recent_corrections ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Corrections</CardTitle>
        <CardDescription>
          Your recent feedback on message classifications and the corrected actions.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {corrections.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">
            No corrections yet. Corrections appear when you provide feedback on message handling.
          </p>
        ) : (
          <div className="space-y-1 border rounded-lg divide-y">
            {corrections.map((correction, idx) => (
              <CorrectionItem key={`${correction.message_text}-${idx}`} correction={correction} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
