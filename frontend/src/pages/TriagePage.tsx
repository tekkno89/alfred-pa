import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  AlertTriangle,
  Clock,
  Archive,
  ExternalLink,
  ThumbsUp,
  ThumbsDown,
  Settings,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useClassifications, useTriageSessionStats, useSubmitFeedback } from '@/hooks/useTriage'
import type { TriageClassification } from '@/types'

const URGENCY_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'urgent', label: 'Urgent' },
  { value: 'review_at_break', label: 'Review at Break' },
  { value: 'digest', label: 'Digest' },
] as const

const URGENCY_BADGE: Record<string, { icon: typeof AlertTriangle; className: string; label: string }> = {
  urgent: {
    icon: AlertTriangle,
    className: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
    label: 'Urgent',
  },
  review_at_break: {
    icon: Clock,
    className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200',
    label: 'Review',
  },
  digest: {
    icon: Archive,
    className: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    label: 'Digest',
  },
}

function ClassificationItem({
  item,
  onFeedback,
}: {
  item: TriageClassification
  onFeedback: (id: string, wasCorrect: boolean) => void
}) {
  const badge = URGENCY_BADGE[item.urgency_level] ?? URGENCY_BADGE.digest
  const Icon = badge.icon

  return (
    <Card>
      <CardContent className="py-3 px-4">
        <div className="flex items-start gap-3">
          {/* Urgency badge */}
          <span
            className={`shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${badge.className}`}
          >
            <Icon className="h-3 w-3" />
            {badge.label}
          </span>

          {/* Content */}
          <div className="flex-1 min-w-0 space-y-1">
            <p className="text-sm">{item.abstract || 'Message'}</p>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span>From: {item.sender_name || item.sender_slack_id}</span>
              <span>{item.classification_path === 'dm' ? 'DM' : `#${item.channel_name || item.channel_id}`}</span>
              {item.created_at && (
                <span>
                  {new Date(item.created_at).toLocaleString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="shrink-0 flex items-center gap-1">
            {item.slack_permalink && (
              <a
                href={item.slack_permalink}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="inline-flex items-center justify-center h-7 w-7 rounded-md hover:bg-accent"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-green-600 hover:text-green-700"
              onClick={() => onFeedback(item.id, true)}
              title="Correct classification"
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-red-600 hover:text-red-700"
              onClick={() => onFeedback(item.id, false)}
              title="Incorrect classification"
            >
              <ThumbsDown className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function TriagePage() {
  const navigate = useNavigate()
  const [urgencyFilter, setUrgencyFilter] = useState('all')
  const [offset, setOffset] = useState(0)
  const limit = 20

  const { data: stats } = useTriageSessionStats()
  const { data: classifications, isLoading } = useClassifications({
    urgency: urgencyFilter === 'all' ? undefined : urgencyFilter,
    limit,
    offset,
  })
  const submitFeedback = useSubmitFeedback()

  const handleFeedback = (classificationId: string, wasCorrect: boolean) => {
    submitFeedback.mutate({
      classification_id: classificationId,
      was_correct: wasCorrect,
    })
  }

  const totalItems = classifications?.total ?? 0
  const hasMore = offset + limit < totalItems

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-3xl mx-auto space-y-4">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => navigate('/')}
              >
                <ArrowLeft className="h-4 w-4" />
              </Button>
              <h1 className="text-xl font-semibold">Slack Triage</h1>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate('/settings/triage')}
            >
              <Settings className="h-3.5 w-3.5 mr-1.5" />
              Settings
            </Button>
          </div>

          {/* Stats bar */}
          {stats && stats.total > 0 && (
            <div className="flex gap-4 text-sm">
              <span className="flex items-center gap-1.5">
                <AlertTriangle className="h-4 w-4 text-red-500" />
                <span className="font-medium">{stats.urgent}</span> urgent
              </span>
              <span className="flex items-center gap-1.5">
                <Clock className="h-4 w-4 text-yellow-500" />
                <span className="font-medium">{stats.review_at_break}</span> review
              </span>
              <span className="flex items-center gap-1.5">
                <Archive className="h-4 w-4 text-slate-500" />
                <span className="font-medium">{stats.digest}</span> digest
              </span>
            </div>
          )}

          {/* Filter */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Filter:</span>
            <Select value={urgencyFilter} onValueChange={(v) => { setUrgencyFilter(v); setOffset(0) }}>
              <SelectTrigger className="w-[180px] h-8 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {URGENCY_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {totalItems > 0 && (
              <span className="text-xs text-muted-foreground ml-auto">
                {totalItems} total
              </span>
            )}
          </div>

          {/* Classifications list */}
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading classifications...</p>
          ) : !classifications || classifications.items.length === 0 ? (
            <div className="text-center py-12 space-y-2">
              <p className="text-muted-foreground">No classifications found</p>
              <p className="text-xs text-muted-foreground">
                Classifications appear here when Slack messages are triaged during focus sessions.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {classifications.items.map((item) => (
                <ClassificationItem
                  key={item.id}
                  item={item}
                  onFeedback={handleFeedback}
                />
              ))}
            </div>
          )}

          {/* Pagination */}
          {totalItems > limit && (
            <div className="flex justify-center gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - limit))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!hasMore}
                onClick={() => setOffset(offset + limit)}
              >
                Next
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
