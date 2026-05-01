import { useState } from 'react'
import {
  ChevronDown,
  ChevronUp,
  Check,
  Clock,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useDigestConversations } from '@/hooks/useConversations'
import { useDigestChildren as useDigestChildrenLegacy } from '@/hooks/useTriage'
import { ConversationSummaryCard } from './ConversationSummaryCard'
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

interface SummaryCardProps {
  summary: TriageClassification
  onMarkReviewed: (id: string) => void
}

export function SummaryCard({ summary, onMarkReviewed }: SummaryCardProps) {
  const [expanded, setExpanded] = useState(false)
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

  const { data: conversationsData, isLoading: loadingConversations } = useDigestConversations(
    expanded ? summary.id : null
  )

  const { data: legacyChildren, isLoading: loadingLegacy } = useDigestChildrenLegacy(
    expanded && (!conversationsData || conversationsData.items.length === 0) ? summary.id : null
  )

  const conversations = conversationsData?.items ?? []
  const hasConversations = conversations.length > 0
  const legacyMessages = legacyChildren ?? []

  const p1Conversations = conversations.filter((c) => c.priority_level === 'p1')
  const p2Conversations = conversations.filter((c) => c.priority_level === 'p2')
  const p3Conversations = conversations.filter((c) => c.priority_level === 'p3')

  const isLoading = loadingConversations || loadingLegacy

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
                {expanded ? abstract : abstract.slice(0, 120) + (abstract.length > 120 ? '...' : '')}
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
                {childCount}
              </Button>
            </div>
          </div>

          {expanded && (
            <div className="mt-3 pt-3 border-t space-y-3">
              {isLoading ? (
                <p className="text-sm text-muted-foreground py-2">Loading...</p>
              ) : hasConversations ? (
                <>
                  {p1Conversations.length > 0 && (
                    <div className="space-y-2">
                      <h4 className="text-sm font-medium text-orange-600 dark:text-orange-400">
                        P1 — Important ({p1Conversations.length})
                      </h4>
                      {p1Conversations.map((conv) => (
                        <ConversationSummaryCard key={conv.id} conversation={conv} />
                      ))}
                    </div>
                  )}

                  {p2Conversations.length > 0 && (
                    <div className="space-y-2">
                      <h4 className="text-sm font-medium text-yellow-600 dark:text-yellow-400">
                        P2 — Notable ({p2Conversations.length})
                      </h4>
                      {p2Conversations.map((conv) => (
                        <ConversationSummaryCard key={conv.id} conversation={conv} />
                      ))}
                    </div>
                  )}

                  {p3Conversations.length > 0 && (
                    <div className="space-y-2">
                      <h4 className="text-sm font-medium text-blue-600 dark:text-blue-400">
                        P3 — Daily Digest ({p3Conversations.length})
                      </h4>
                      {p3Conversations.map((conv) => (
                        <ConversationSummaryCard key={conv.id} conversation={conv} />
                      ))}
                    </div>
                  )}
                </>
              ) : legacyMessages.length > 0 ? (
                <p className="text-sm text-muted-foreground py-2">
                  {legacyMessages.length} messages (ungrouped)
                </p>
              ) : (
                <p className="text-sm text-muted-foreground py-2">No messages found</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </>
  )
}
