import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  AlertTriangle,
  ExternalLink,
  Check,
  Settings,
  AlertCircle,
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
import {
  useClassifications,
  useMarkReviewed,
  useMarkAllReviewed,
  useTriageSessionStats,
  type TriageFilter,
} from '@/hooks/useTriage'
import { SummaryCard } from '@/components/triage/SummaryCard'
import { ClassificationDetailModal } from '@/components/triage/ClassificationDetailModal'
import type { TriageClassification } from '@/types'

const FILTER_OPTIONS: { value: TriageFilter; label: string }[] = [
  { value: 'needs_attention', label: 'Needs Attention' },
  { value: 'p0', label: 'P0 Alerts' },
  { value: 'focus', label: 'Focus Sessions' },
  { value: 'scheduled', label: 'Scheduled Digests' },
  { value: 'review', label: 'Review' },
  { value: 'reviewed', label: 'Reviewed' },
]

function P0AlertCard({
  item,
  onClick,
  onMarkReviewed,
}: {
  item: TriageClassification
  onClick: () => void
  onMarkReviewed: (id: string) => void
}) {
  const isReviewed = !!item.reviewed_at

  return (
    <Card
      className={`cursor-pointer hover:bg-accent/50 transition-colors ${
        isReviewed ? 'opacity-60' : ''
      }`}
      onClick={onClick}
    >
      <CardContent className="py-3 px-4">
        <div className="flex items-start gap-3">
          <span className="shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200">
            <AlertTriangle className="h-3 w-3" />
            P0
          </span>

          <div className="flex-1 min-w-0 space-y-1">
            <p className="text-sm">{item.abstract || 'Message'}</p>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span>From: {item.sender_name || item.sender_slack_id}</span>
              <span>
                {item.classification_path === 'dm'
                  ? 'DM'
                  : `#${item.channel_name || item.channel_id}`}
              </span>
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
  const [filter, setFilter] = useState<TriageFilter>('needs_attention')
  const [offset, setOffset] = useState(0)
  const [selectedItem, setSelectedItem] = useState<TriageClassification | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const limit = 20

  const { data: stats } = useTriageSessionStats()
  const { data: classifications, isLoading } = useClassifications({
    filter,
    limit,
    offset,
  })
  const markReviewed = useMarkReviewed()
  const markAllReviewed = useMarkAllReviewed()

  const handleMarkReviewed = (id: string) => {
    markReviewed.mutate({
      classification_ids: [id],
      reviewed: true,
    })
  }

  const handleMarkAllReviewed = () => {
    if (filter === 'p0' || filter === 'reviewed') return
    markAllReviewed.mutate({ filter })
  }

  const handleCardClick = (item: TriageClassification) => {
    setSelectedItem(item)
    setModalOpen(true)
  }

  const totalItems = classifications?.total ?? 0
  const hasMore = offset + limit < totalItems

  const items = classifications?.items ?? []
  const p0Items = items.filter((item) => item.priority_level === 'p0')
  const summaries = items.filter((item) => item.priority_level === 'digest_summary')

  const canMarkAllReviewed = filter !== 'p0' && filter !== 'reviewed'
  const hasUnreviewed =
    filter !== 'reviewed' && (p0Items.some((i) => !i.reviewed_at) || summaries.some((i) => !i.reviewed_at))

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
              <button
                className={`flex items-center gap-1.5 hover:underline ${
                  filter === 'p0' ? 'underline' : ''
                }`}
                onClick={() => {
                  setFilter(filter === 'p0' ? 'needs_attention' : 'p0')
                  setOffset(0)
                }}
              >
                <AlertTriangle className="h-4 w-4 text-red-500" />
                <span className="font-medium">{stats.p0}</span> P0
              </button>
              <button
                className={`flex items-center gap-1.5 hover:underline ${
                  filter === 'review' ? 'underline' : ''
                }`}
                onClick={() => {
                  setFilter(filter === 'review' ? 'needs_attention' : 'review')
                  setOffset(0)
                }}
              >
                <AlertCircle className="h-4 w-4 text-yellow-500" />
                <span className="font-medium">{stats.review}</span> review
              </button>
            </div>
          )}

          {/* Filters */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Filter:</span>
              <Select
                value={filter}
                onValueChange={(v) => {
                  setFilter(v as TriageFilter)
                  setOffset(0)
                }}
              >
                <SelectTrigger className="w-[180px] h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FILTER_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {hasUnreviewed && canMarkAllReviewed && (
              <Button
                variant="outline"
                size="sm"
                className="h-8"
                onClick={handleMarkAllReviewed}
                disabled={markAllReviewed.isPending}
              >
                <Check className="h-3.5 w-3.5 mr-1.5" />
                Mark All Reviewed
              </Button>
            )}
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
                Classifications appear here when Slack messages are triaged during focus
                sessions or scheduled digests.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {/* P0 Alerts Section */}
              {p0Items.length > 0 && (
                <div className="space-y-2">
                  {p0Items.length > 1 && (
                    <h2 className="text-sm font-medium text-muted-foreground">
                      P0 Alerts ({p0Items.length})
                    </h2>
                  )}
                  {p0Items.map((item) => (
                    <P0AlertCard
                      key={item.id}
                      item={item}
                      onClick={() => handleCardClick(item)}
                      onMarkReviewed={handleMarkReviewed}
                    />
                  ))}
                </div>
              )}

              {/* Summaries Section */}
              {summaries.length > 0 && (
                <div className="space-y-2">
                  {p0Items.length > 0 && summaries.length > 0 && (
                    <h2 className="text-sm font-medium text-muted-foreground pt-2">
                      Summaries ({summaries.length})
                    </h2>
                  )}
                  {summaries.map((summary) => (
                    <SummaryCard
                      key={summary.id}
                      summary={summary}
                      onMarkReviewed={handleMarkReviewed}
                    />
                  ))}
                </div>
              )}
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
