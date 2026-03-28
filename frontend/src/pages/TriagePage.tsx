import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  AlertTriangle,
  Eye,
  ExternalLink,
  Check,
  CheckCircle,
  Settings,
  VolumeX,
  Layers,
  AlertCircle,
  Bookmark,
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
import { useClassifications, useTriageSessionStats, useMarkReviewed } from '@/hooks/useTriage'
import { ClassificationDetailModal } from '@/components/triage/ClassificationDetailModal'
import type { TriageClassification } from '@/types'

const PRIORITY_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'needs_attention', label: 'Needs Attention' },
  { value: 'p0', label: 'P0 — Urgent' },
  { value: 'p1', label: 'P1 — Important' },
  { value: 'p2', label: 'P2 — Notable' },
  { value: 'p3', label: 'P3 — Low' },
  { value: 'digest_summary', label: 'Session Digest' },
  { value: 'review', label: 'Needs Review' },
] as const

const STATUS_OPTIONS = [
  { value: 'unreviewed', label: 'Unreviewed' },
  { value: 'reviewed', label: 'Reviewed' },
  { value: 'all', label: 'All' },
] as const

const PRIORITY_BADGE: Record<string, { icon: typeof AlertTriangle; className: string; label: string }> = {
  p0: {
    icon: AlertTriangle,
    className: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
    label: 'P0',
  },
  p1: {
    icon: AlertCircle,
    className: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200',
    label: 'P1',
  },
  p2: {
    icon: Bookmark,
    className: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
    label: 'P2',
  },
  p3: {
    icon: VolumeX,
    className: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
    label: 'P3',
  },
  digest_summary: {
    icon: Layers,
    className: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
    label: 'Session Digest',
  },
  review: {
    icon: Eye,
    className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200',
    label: 'Review',
  },
}

function ClassificationItem({
  item,
  onClick,
  onMarkReviewed,
}: {
  item: TriageClassification
  onClick: () => void
  onMarkReviewed: (id: string) => void
}) {
  const badge = PRIORITY_BADGE[item.priority_level] ?? PRIORITY_BADGE.p2
  const Icon = badge.icon
  const isReviewed = !!item.reviewed_at

  return (
    <Card
      className={`cursor-pointer hover:bg-accent/50 transition-colors ${isReviewed ? 'opacity-60' : ''}`}
      onClick={onClick}
    >
      <CardContent className="py-3 px-4">
        <div className="flex items-start gap-3">
          {/* Priority badge */}
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
              {item.priority_level === 'digest_summary' && item.child_count ? (
                <span className="font-medium">{item.child_count} messages</span>
              ) : (
                <span>From: {item.sender_name || item.sender_slack_id}</span>
              )}
              <span>{item.priority_level === 'digest_summary'
                ? (item.classification_path === 'pomodoro' ? 'Pomodoro' : 'Focus')
                : (item.classification_path === 'dm' ? 'DM' : `#${item.channel_name || item.channel_id}`)}</span>
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
              {isReviewed && (
                <span className="inline-flex items-center gap-0.5 text-green-600 dark:text-green-400">
                  <CheckCircle className="h-3 w-3" />
                  Reviewed
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
            {!isReviewed && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-muted-foreground hover:text-green-600"
                onClick={(e) => {
                  e.stopPropagation()
                  onMarkReviewed(item.id)
                }}
                title="Mark as reviewed"
              >
                <Check className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function TriagePage() {
  const navigate = useNavigate()
  const [priorityFilter, setPriorityFilter] = useState('needs_attention')
  const [statusFilter, setStatusFilter] = useState('unreviewed')
  const [offset, setOffset] = useState(0)
  const [selectedItem, setSelectedItem] = useState<TriageClassification | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const limit = 20

  const reviewed =
    statusFilter === 'reviewed' ? true : statusFilter === 'unreviewed' ? false : undefined

  const { data: stats } = useTriageSessionStats()
  const { data: classifications, isLoading } = useClassifications({
    priority: priorityFilter === 'all' ? undefined : priorityFilter,
    reviewed,
    hide_active_digest: false,
    limit,
    offset,
  })
  const markReviewed = useMarkReviewed()

  const handleMarkReviewed = (id: string) => {
    markReviewed.mutate({
      classification_ids: [id],
      reviewed: true,
    })
  }

  const handleCardClick = (item: TriageClassification) => {
    setSelectedItem(item)
    setModalOpen(true)
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
              <button className={`flex items-center gap-1.5 hover:underline ${priorityFilter === 'p0' ? 'underline' : ''}`} onClick={() => { setPriorityFilter(priorityFilter === 'p0' ? 'needs_attention' : 'p0'); setOffset(0) }}>
                <AlertTriangle className="h-4 w-4 text-red-500" />
                <span className="font-medium">{stats.p0}</span> P0
              </button>
              <button className={`flex items-center gap-1.5 hover:underline ${priorityFilter === 'p1' ? 'underline' : ''}`} onClick={() => { setPriorityFilter(priorityFilter === 'p1' ? 'needs_attention' : 'p1'); setOffset(0) }}>
                <AlertCircle className="h-4 w-4 text-orange-500" />
                <span className="font-medium">{stats.p1}</span> P1
              </button>
              <button className={`flex items-center gap-1.5 hover:underline ${priorityFilter === 'p2' ? 'underline' : ''}`} onClick={() => { setPriorityFilter(priorityFilter === 'p2' ? 'needs_attention' : 'p2'); setOffset(0) }}>
                <Bookmark className="h-4 w-4 text-blue-500" />
                <span className="font-medium">{stats.p2}</span> P2
              </button>
              <button className={`flex items-center gap-1.5 hover:underline ${priorityFilter === 'review' ? 'underline' : ''}`} onClick={() => { setPriorityFilter(priorityFilter === 'review' ? 'needs_attention' : 'review'); setOffset(0) }}>
                <Eye className="h-4 w-4 text-yellow-500" />
                <span className="font-medium">{stats.review}</span> review
              </button>
            </div>
          )}

          {/* Filters */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Status:</span>
              <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setOffset(0) }}>
                <SelectTrigger className="w-[140px] h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Priority:</span>
              <Select value={priorityFilter} onValueChange={(v) => { setPriorityFilter(v); setOffset(0) }}>
                <SelectTrigger className="w-[180px] h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PRIORITY_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
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
                  onClick={() => handleCardClick(item)}
                  onMarkReviewed={handleMarkReviewed}
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

      {/* Detail modal */}
      <ClassificationDetailModal
        classification={selectedItem}
        open={modalOpen}
        onOpenChange={setModalOpen}
      />
    </div>
  )
}
