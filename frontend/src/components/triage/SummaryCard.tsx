import { useState } from 'react'
import {
  ChevronDown,
  ChevronUp,
  Check,
  ExternalLink,
  Clock,
  AlertTriangle,
  AlertCircle,
  Bookmark,
  Eye,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useDigestChildren } from '@/hooks/useTriage'
import { CorrectClassificationDialog } from './CorrectClassificationDialog'
import type { TriageClassification } from '@/types'

const DIGEST_TYPE_LABELS: Record<string, { label: string; icon: typeof Clock; className: string }> = {
  focus: {
    label: 'Focus Session',
    icon: Clock,
    className: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200',
  },
  scheduled: {
    label: 'Scheduled Digest',
    icon: Clock,
    className: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/40 dark:text-cyan-200',
  },
}

const PRIORITY_BADGE: Record<string, { icon: typeof AlertTriangle; className: string }> = {
  p0: { icon: AlertTriangle, className: 'text-red-500' },
  p1: { icon: AlertCircle, className: 'text-orange-500' },
  p2: { icon: Bookmark, className: 'text-blue-500' },
  review: { icon: Eye, className: 'text-yellow-500' },
}

function truncateToTwoLines(text: string, maxChars: number = 120): string {
  if (text.length <= maxChars) return text
  const truncated = text.slice(0, maxChars)
  const lastSpace = truncated.lastIndexOf(' ')
  return truncated.slice(0, lastSpace > 0 ? lastSpace : maxChars) + '...'
}

function ChildMessageItem({
  item,
  onMarkReviewed,
  onCorrect,
}: {
  item: TriageClassification
  onMarkReviewed: (id: string) => void
  onCorrect: (item: TriageClassification) => void
}) {
  const badge = PRIORITY_BADGE[item.priority_level] ?? PRIORITY_BADGE.p2
  const Icon = badge.icon
  const isReviewed = !!item.reviewed_at

  return (
    <div
      className={`flex items-start gap-3 py-2 px-3 rounded-md hover:bg-accent/50 cursor-pointer ${
        isReviewed ? 'opacity-60' : ''
      }`}
      onClick={() => onCorrect(item)}
    >
      <span className={`shrink-0 ${badge.className}`}>
        <Icon className="h-4 w-4" />
      </span>
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
      <div className="shrink-0 flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
        {item.slack_permalink && (
          <a
            href={item.slack_permalink}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center h-7 w-7 rounded-md hover:bg-accent"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
        {!isReviewed && (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-green-600"
            onClick={() => onMarkReviewed(item.id)}
            title="Mark as reviewed"
          >
            <Check className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </div>
  )
}

interface SummaryCardProps {
  summary: TriageClassification
  onMarkReviewed: (id: string) => void
}

export function SummaryCard({ summary, onMarkReviewed }: SummaryCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [correctingItem, setCorrectingItem] = useState<TriageClassification | null>(null)
  const { data: children, isLoading } = useDigestChildren(expanded ? summary.id : null)
  const isReviewed = !!summary.reviewed_at

  const digestType = summary.digest_type || 'focus'
  const typeInfo = DIGEST_TYPE_LABELS[digestType] ?? DIGEST_TYPE_LABELS.focus
  const TypeIcon = typeInfo.icon

  const createdAt = summary.created_at
    ? new Date(summary.created_at).toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : ''

  const childCount = summary.child_count || 0
  const abstract = summary.abstract || `${childCount} messages`

  return (
    <>
      <Card className={isReviewed ? 'opacity-60' : ''}>
        <CardContent className="py-3 px-4">
          <div
            className="flex items-start gap-3 cursor-pointer"
            onClick={() => setExpanded(!expanded)}
          >
            <Badge variant="secondary" className={typeInfo.className}>
              <TypeIcon className="h-3 w-3 mr-1" />
              {typeInfo.label}
            </Badge>

            <div className="flex-1 min-w-0 space-y-1">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>{createdAt}</span>
                <span>•</span>
                <span>{childCount} messages</span>
              </div>
              <p className="text-sm">
                {expanded ? abstract : truncateToTwoLines(abstract)}
              </p>
            </div>

            <div className="shrink-0 flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
              {!isReviewed && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs text-muted-foreground hover:text-green-600"
                  onClick={() => onMarkReviewed(summary.id)}
                >
                  <Check className="h-3.5 w-3.5 mr-1" />
                  Mark Reviewed
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="h-7"
                onClick={() => setExpanded(!expanded)}
              >
                {expanded ? (
                  <ChevronUp className="h-4 w-4 mr-1" />
                ) : (
                  <ChevronDown className="h-4 w-4 mr-1" />
                )}
                {childCount} messages
              </Button>
            </div>
          </div>

          {expanded && (
            <div className="mt-3 pt-3 border-t space-y-1">
              {isLoading ? (
                <p className="text-sm text-muted-foreground py-2">Loading messages...</p>
              ) : children && children.length > 0 ? (
                children.map((child) => (
                  <ChildMessageItem
                    key={child.id}
                    item={child}
                    onMarkReviewed={onMarkReviewed}
                    onCorrect={setCorrectingItem}
                  />
                ))
              ) : (
                <p className="text-sm text-muted-foreground py-2">No messages found</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <CorrectClassificationDialog
        classification={correctingItem}
        open={!!correctingItem}
        onOpenChange={(open) => !open && setCorrectingItem(null)}
      />
    </>
  )
}
