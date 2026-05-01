import { useState } from 'react'
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  MessageSquare,
  Hash,
  Clock,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useConversationMessages } from '@/hooks/useConversations'
import { CorrectClassificationDialog } from './CorrectClassificationDialog'
import type { ConversationSummary, TriageClassification } from '@/types'

const PRIORITY_ICONS: Record<string, { icon: typeof Clock; className: string; bgClassName: string }> = {
  p1: {
    icon: Clock,
    className: 'text-orange-500',
    bgClassName: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200',
  },
  p2: {
    icon: Clock,
    className: 'text-yellow-500',
    bgClassName: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200',
  },
  p3: {
    icon: Clock,
    className: 'text-blue-500',
    bgClassName: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
  },
}

const TYPE_ICONS: Record<string, typeof MessageSquare> = {
  thread: MessageSquare,
  dm: MessageSquare,
  channel: Hash,
}

function truncateText(text: string, maxChars: number = 150): string {
  if (text.length <= maxChars) return text
  const truncated = text.slice(0, maxChars)
  const lastSpace = truncated.lastIndexOf(' ')
  return truncated.slice(0, lastSpace > 0 ? lastSpace : maxChars) + '...'
}

function ChildMessageItem({
  item,
  onCorrect,
}: {
  item: TriageClassification
  onCorrect: (item: TriageClassification) => void
}) {
  return (
    <div
      className="flex items-start gap-3 py-2 px-3 rounded-md hover:bg-accent/50 cursor-pointer"
      onClick={() => onCorrect(item)}
    >
      <div className="flex-1 min-w-0 space-y-1">
        <p className="text-sm">{item.abstract || 'Message'}</p>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>From: {item.sender_name || item.sender_slack_id}</span>
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
      </div>
    </div>
  )
}

interface ConversationSummaryCardProps {
  conversation: ConversationSummary
}

export function ConversationSummaryCard({ conversation }: ConversationSummaryCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [correctingItem, setCorrectingItem] = useState<TriageClassification | null>(null)
  const { data: messagesData, isLoading } = useConversationMessages(
    expanded ? conversation.id : null
  )

  const priorityConfig = PRIORITY_ICONS[conversation.priority_level] ?? PRIORITY_ICONS.p3
  const PriorityIcon = priorityConfig.icon
  const TypeIcon = TYPE_ICONS[conversation.conversation_type] ?? MessageSquare

  const typeLabel =
    conversation.conversation_type === 'thread'
      ? 'Thread'
      : conversation.conversation_type === 'dm'
        ? 'DM'
        : 'Chat'

  const channelDisplay =
    conversation.conversation_type === 'dm'
      ? 'Direct Message'
      : `#${conversation.channel_name || conversation.channel_id}`

  const participantNames = conversation.participants
    .slice(0, 3)
    .map((p) => p.name || p.slack_id)
    .join(', ')
  const moreParticipants =
    conversation.participants.length > 3
      ? ` +${conversation.participants.length - 3} more`
      : ''

  const createdAt = conversation.created_at
    ? new Date(conversation.created_at).toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : ''

  return (
    <>
      <Card className={conversation.reviewed_at ? 'opacity-60' : ''}>
        <CardContent className="py-3 px-4">
          <div
            className="flex items-start gap-3 cursor-pointer"
            onClick={() => setExpanded(!expanded)}
          >
            <Badge variant="secondary" className={priorityConfig.bgClassName}>
              <PriorityIcon className="h-3 w-3 mr-1" />
              {conversation.priority_level.toUpperCase()}
            </Badge>

            <div className="flex-1 min-w-0 space-y-1">
              <div className="flex items-center gap-2 text-sm">
                <TypeIcon className="h-4 w-4 text-muted-foreground" />
                <span className="font-medium">{typeLabel}</span>
                <span className="text-muted-foreground">in</span>
                <span className="font-medium">{channelDisplay}</span>
              </div>

              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>{createdAt}</span>
                <span>•</span>
                <span>{conversation.message_count} messages</span>
                {conversation.participants.length > 0 && (
                  <>
                    <span>•</span>
                    <span>
                      {participantNames}
                      {moreParticipants}
                    </span>
                  </>
                )}
              </div>

              <p className="text-sm">
                {expanded
                  ? conversation.abstract
                  : truncateText(conversation.abstract)}
              </p>
            </div>

            <div className="shrink-0 flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
              {conversation.slack_permalink && (
                <a
                  href={conversation.slack_permalink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center justify-center h-7 w-7 rounded-md hover:bg-accent"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
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
                {conversation.message_count}
              </Button>
            </div>
          </div>

          {expanded && (
            <div className="mt-3 pt-3 border-t space-y-1">
              {isLoading ? (
                <p className="text-sm text-muted-foreground py-2">Loading messages...</p>
              ) : messagesData && messagesData.items.length > 0 ? (
                messagesData.items.map((item) => (
                  <ChildMessageItem
                    key={item.id}
                    item={item}
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
