import { useState, useEffect } from 'react'
import {
  AlertTriangle,
  Clock,
  Archive,
  ExternalLink,
  ThumbsUp,
  ThumbsDown,
  CheckCircle,
  CircleDashed,
  VolumeX,
  Layers,
} from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useSubmitFeedback, useMarkReviewed, useDigestChildren } from '@/hooks/useTriage'
import type { TriageClassification, UrgencyLevel } from '@/types'

const URGENCY_CONFIG: Record<string, { icon: typeof AlertTriangle; className: string; label: string }> = {
  urgent: {
    icon: AlertTriangle,
    className: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
    label: 'Urgent',
  },
  digest: {
    icon: Archive,
    className: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    label: 'Digest',
  },
  digest_summary: {
    icon: Layers,
    className: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
    label: 'Session Digest',
  },
  noise: {
    icon: VolumeX,
    className: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
    label: 'Noise',
  },
  review: {
    icon: Clock,
    className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200',
    label: 'Unclassified',
  },
}

interface ClassificationDetailModalProps {
  classification: TriageClassification | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ClassificationDetailModal({
  classification,
  open,
  onOpenChange,
}: ClassificationDetailModalProps) {
  const [feedbackGiven, setFeedbackGiven] = useState<boolean | null>(null)
  const [correctUrgency, setCorrectUrgency] = useState<string | undefined>(undefined)
  const submitFeedback = useSubmitFeedback()
  const markReviewed = useMarkReviewed()
  const isDigestSummary = classification?.urgency_level === 'digest_summary'
  const { data: digestChildren } = useDigestChildren(
    isDigestSummary ? classification?.id ?? null : null
  )

  // Reset feedback state when a different classification is shown
  useEffect(() => {
    setFeedbackGiven(null)
    setCorrectUrgency(undefined)
  }, [classification?.id])

  if (!classification) return null

  const badge = URGENCY_CONFIG[classification.urgency_level] ?? URGENCY_CONFIG.digest
  const Icon = badge.icon
  const isReviewed = !!classification.reviewed_at

  const handleFeedback = (wasCorrect: boolean) => {
    setFeedbackGiven(wasCorrect)
    submitFeedback.mutate({
      classification_id: classification.id,
      was_correct: wasCorrect,
      correct_urgency: wasCorrect ? undefined : (correctUrgency as UrgencyLevel | undefined),
    })
  }

  const handleToggleReviewed = () => {
    markReviewed.mutate(
      {
        classification_ids: [classification.id],
        reviewed: !isReviewed,
      },
      {
        onSuccess: () => {
          onOpenChange(false)
        },
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Badge variant="outline" className={badge.className}>
              <Icon className="h-3 w-3 mr-1" />
              {badge.label}
            </Badge>
            <span className="text-sm font-normal text-muted-foreground">
              {classification.confidence > 0 && `${Math.round(classification.confidence * 100)}% confidence`}
            </span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {isDigestSummary ? (
            <>
              {/* Digest summary metadata */}
              <div className="flex items-center gap-4 text-sm text-muted-foreground">
                <span>
                  {classification.classification_path === 'pomodoro' ? 'Pomodoro' : 'Focus'} session
                </span>
                {classification.focus_started_at && (
                  <span>
                    Started {new Date(classification.focus_started_at).toLocaleString(undefined, {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                )}
              </div>

              {/* Digest children as clickable cards */}
              {digestChildren && digestChildren.length > 0 && (
                <div>
                  <p className="text-sm font-medium mb-2">
                    Messages ({digestChildren.length})
                  </p>
                  <div className="max-h-72 overflow-y-auto space-y-2">
                    {digestChildren.map((child) => (
                      <div
                        key={child.id}
                        role={child.slack_permalink ? 'link' : undefined}
                        className={`text-sm bg-muted/50 rounded-md p-2 space-y-1 transition-colors ${
                          child.slack_permalink ? 'hover:bg-muted cursor-pointer' : ''
                        }`}
                        onClick={() => {
                          if (child.slack_permalink) {
                            window.open(child.slack_permalink, '_blank', 'noopener,noreferrer')
                          }
                        }}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium truncate">
                            {child.sender_name || child.sender_slack_id}
                          </span>
                          <div className="flex items-center gap-2 shrink-0 text-xs text-muted-foreground">
                            <span>
                              {child.classification_path === 'dm'
                                ? 'DM'
                                : `#${child.channel_name || child.channel_id}`}
                            </span>
                            {child.created_at && (
                              <span>
                                {new Date(child.created_at).toLocaleTimeString(undefined, {
                                  hour: '2-digit',
                                  minute: '2-digit',
                                })}
                              </span>
                            )}
                            {child.slack_permalink && (
                              <ExternalLink className="h-3 w-3 text-primary" />
                            )}
                          </div>
                        </div>
                        <p className="text-muted-foreground">{child.abstract || 'Message'}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              {/* Abstract */}
              <div>
                <p className="text-sm">{classification.abstract || 'No summary available'}</p>
              </div>

              {/* Metadata */}
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-muted-foreground">From:</span>{' '}
                  {classification.sender_name || classification.sender_slack_id}
                </div>
                <div>
                  <span className="text-muted-foreground">Channel:</span>{' '}
                  {classification.classification_path === 'dm'
                    ? 'DM'
                    : `#${classification.channel_name || classification.channel_id}`}
                </div>
                {classification.created_at && (
                  <div className="col-span-2">
                    <span className="text-muted-foreground">Time:</span>{' '}
                    {new Date(classification.created_at).toLocaleString()}
                  </div>
                )}
              </div>

              {/* Classification reason */}
              {classification.classification_reason && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Classification reason</p>
                  <p className="text-sm bg-muted/50 rounded-md p-2">{classification.classification_reason}</p>
                </div>
              )}

              {/* Slack link */}
              {classification.slack_permalink && (
                <a
                  href={classification.slack_permalink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  Open in Slack
                </a>
              )}
            </>
          )}

          {/* Feedback section */}
          {!isDigestSummary && (
          <div className="border-t pt-3">
            <p className="text-sm font-medium mb-2">Was this triaged correctly?</p>
            <div className="flex items-center gap-2">
              <Button
                variant={feedbackGiven === true ? 'default' : 'outline'}
                size="sm"
                onClick={() => handleFeedback(true)}
                disabled={submitFeedback.isPending || feedbackGiven !== null}
              >
                <ThumbsUp className="h-3.5 w-3.5 mr-1.5" />
                Yes
              </Button>
              <Button
                variant={feedbackGiven === false ? 'default' : 'outline'}
                size="sm"
                onClick={() => {
                  setFeedbackGiven(false)
                }}
                disabled={submitFeedback.isPending || feedbackGiven !== null}
              >
                <ThumbsDown className="h-3.5 w-3.5 mr-1.5" />
                No
              </Button>
              {feedbackGiven === false && !correctUrgency && (
                <Select onValueChange={(v) => {
                  setCorrectUrgency(v)
                  submitFeedback.mutate({
                    classification_id: classification.id,
                    was_correct: false,
                    correct_urgency: v as UrgencyLevel,
                  })
                }}>
                  <SelectTrigger className="w-[160px] h-8 text-sm">
                    <SelectValue placeholder="Correct level..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="urgent">Urgent</SelectItem>
                    <SelectItem value="digest">Digest</SelectItem>
                    <SelectItem value="noise">Noise</SelectItem>
                    <SelectItem value="review">Unclassified</SelectItem>
                  </SelectContent>
                </Select>
              )}
            </div>
          </div>
          )}

          {/* Review toggle */}
          <div className="border-t pt-3 flex justify-end">
            <Button
              variant="outline"
              size="sm"
              onClick={handleToggleReviewed}
              disabled={markReviewed.isPending}
            >
              {isReviewed ? (
                <>
                  <CircleDashed className="h-3.5 w-3.5 mr-1.5" />
                  Mark as Unreviewed
                </>
              ) : (
                <>
                  <CheckCircle className="h-3.5 w-3.5 mr-1.5" />
                  Mark as Reviewed
                </>
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
