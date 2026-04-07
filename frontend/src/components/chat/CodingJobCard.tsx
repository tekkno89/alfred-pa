import { useState } from 'react'
import { Code, ChevronRight, Loader2, GitPullRequest, AlertTriangle, XCircle, CheckCircle2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useCodingJob, useApprovePlan, useApproveImpl, useCancelCodingJob, useRequestRevision } from '@/hooks/useCodingJobs'
import type { CodingJobStatus } from '@/types'

interface CodingJobCardProps {
  jobId: string
  repo: string
  taskDescription?: string
  question?: string
}

const STATUS_CONFIG: Record<CodingJobStatus, { label: string; icon: typeof Code; color: string }> = {
  pending_plan_approval: { label: 'Awaiting Approval', icon: Code, color: 'text-yellow-500' },
  planning: { label: 'Planning...', icon: Loader2, color: 'text-blue-500' },
  plan_ready: { label: 'Plan Ready', icon: CheckCircle2, color: 'text-green-500' },
  pending_impl_approval: { label: 'Awaiting Approval', icon: Code, color: 'text-yellow-500' },
  implementing: { label: 'Implementing...', icon: Loader2, color: 'text-blue-500' },
  reviewing: { label: 'Reviewing...', icon: Loader2, color: 'text-blue-500' },
  complete: { label: 'Complete', icon: CheckCircle2, color: 'text-green-500' },
  failed: { label: 'Failed', icon: AlertTriangle, color: 'text-red-500' },
  cancelled: { label: 'Cancelled', icon: XCircle, color: 'text-muted-foreground' },
  exploring: { label: 'Exploring...', icon: Loader2, color: 'text-blue-500' },
}

export function CodingJobCard({ jobId, repo, taskDescription, question }: CodingJobCardProps) {
  const { data: job } = useCodingJob(jobId)
  const approvePlan = useApprovePlan()
  const approveImpl = useApproveImpl()
  const cancelJob = useCancelCodingJob()
  const requestRevision = useRequestRevision()

  const [planExpanded, setPlanExpanded] = useState(false)
  const [reviewExpanded, setReviewExpanded] = useState(false)
  const [revisionText, setRevisionText] = useState('')
  const [showRevisionInput, setShowRevisionInput] = useState(false)

  const status = job?.status ?? 'pending_plan_approval'
  const config = STATUS_CONFIG[status]
  const Icon = config.icon
  const isWorking = ['planning', 'implementing', 'reviewing', 'exploring'].includes(status)
  const isTerminal = ['complete', 'failed', 'cancelled'].includes(status)

  const description = job?.task_description ?? taskDescription ?? question ?? ''

  return (
    <div className="py-3 px-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div className="rounded-lg border bg-card p-4 space-y-3">
        {/* Header */}
        <div className="flex items-center gap-2">
          <Icon className={`h-4 w-4 ${config.color} ${isWorking ? 'animate-spin' : ''}`} />
          <span className={`text-sm font-medium ${config.color}`}>{config.label}</span>
          <span className="text-xs text-muted-foreground ml-auto font-mono">{repo}</span>
        </div>

        {/* Task description */}
        <p className="text-sm text-foreground">{description}</p>

        {/* Error details */}
        {status === 'failed' && job?.error_details && (
          <p className="text-sm text-red-500 bg-red-500/10 rounded p-2">
            {job.error_details.slice(0, 500)}
          </p>
        )}

        {/* Plan content (collapsible) */}
        {job?.plan_content && status !== 'exploring' && (
          <div>
            <button
              onClick={() => setPlanExpanded(!planExpanded)}
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ChevronRight
                className={`h-3 w-3 transition-transform duration-200 ${planExpanded ? 'rotate-90' : ''}`}
              />
              <span>View Plan</span>
            </button>
            {planExpanded && (
              <div className="mt-2 text-sm bg-muted/50 rounded p-3 max-h-96 overflow-y-auto animate-in fade-in slide-in-from-top-1 duration-200">
                <pre className="whitespace-pre-wrap font-mono text-xs">{job.plan_content}</pre>
              </div>
            )}
          </div>
        )}

        {/* Exploration answers are displayed as regular chat messages below the card */}

        {/* PR link */}
        {job?.pr_url && (
          <a
            href={job.pr_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 text-sm text-blue-500 hover:underline"
          >
            <GitPullRequest className="h-4 w-4" />
            {job.repo_full_name}#{job.pr_number ?? 'PR'}
          </a>
        )}

        {/* Review content (collapsible) */}
        {job?.review_content && (
          <div>
            <button
              onClick={() => setReviewExpanded(!reviewExpanded)}
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ChevronRight
                className={`h-3 w-3 transition-transform duration-200 ${reviewExpanded ? 'rotate-90' : ''}`}
              />
              <span>View Review</span>
            </button>
            {reviewExpanded && (
              <div className="mt-2 text-sm bg-muted/50 rounded p-3 max-h-96 overflow-y-auto animate-in fade-in slide-in-from-top-1 duration-200">
                <pre className="whitespace-pre-wrap font-mono text-xs">{job.review_content}</pre>
              </div>
            )}
          </div>
        )}

        {/* Action buttons */}
        {!isTerminal && (
          <div className="flex items-center gap-2 pt-1">
            {status === 'pending_plan_approval' && (
              <>
                <Button
                  size="sm"
                  onClick={() => approvePlan.mutate(jobId)}
                  disabled={approvePlan.isPending}
                >
                  {approvePlan.isPending ? 'Starting...' : 'Approve Planning'}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => cancelJob.mutate(jobId)}
                  disabled={cancelJob.isPending}
                >
                  Cancel
                </Button>
              </>
            )}

            {status === 'plan_ready' && (
              <>
                <Button
                  size="sm"
                  onClick={() => approveImpl.mutate(jobId)}
                  disabled={approveImpl.isPending}
                >
                  {approveImpl.isPending ? 'Starting...' : 'Approve Implementation'}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => cancelJob.mutate(jobId)}
                  disabled={cancelJob.isPending}
                >
                  Cancel
                </Button>
              </>
            )}

            {isWorking && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => cancelJob.mutate(jobId)}
                disabled={cancelJob.isPending}
              >
                {cancelJob.isPending ? 'Cancelling...' : 'Cancel'}
              </Button>
            )}
          </div>
        )}

        {/* Request revision (for completed jobs) */}
        {status === 'complete' && job?.mode !== 'explore' && (
          <div className="pt-1">
            {!showRevisionInput ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowRevisionInput(true)}
              >
                Request Changes
              </Button>
            ) : (
              <div className="space-y-2">
                <textarea
                  className="w-full rounded border bg-background p-2 text-sm resize-none"
                  rows={3}
                  placeholder="Describe the changes you'd like..."
                  value={revisionText}
                  onChange={(e) => setRevisionText(e.target.value)}
                />
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    onClick={() => {
                      if (revisionText.trim()) {
                        requestRevision.mutate({ jobId, description: revisionText.trim() })
                        setRevisionText('')
                        setShowRevisionInput(false)
                      }
                    }}
                    disabled={requestRevision.isPending || !revisionText.trim()}
                  >
                    {requestRevision.isPending ? 'Submitting...' : 'Submit'}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setShowRevisionInput(false)
                      setRevisionText('')
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
