import { useState } from 'react'
import { Sparkles, Loader2, MessageSquare, ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Link2, Plus, X } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useGenerateDefinitions, useSampleCalibrationMessages, useGenerateDefinitionsFromCalibration, useFetchMessageByLink } from '@/hooks/useTriage'
import type { GenerateDefinitionsResponse, CalibrationMessage, CalibrationRating } from '@/types'

interface ClassifierWizardModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onApply: (definitions: GenerateDefinitionsResponse) => void
}

const QUESTIONS_STEPS = [
  {
    label: 'Your Role',
    question: 'What is your role?',
    placeholder: 'e.g. Engineering manager at a startup, overseeing 3 teams',
    field: 'role' as const,
  },
  {
    label: 'Critical Messages',
    question: 'What kind of messages are critical for you?',
    placeholder: 'e.g. Production incidents, messages from my VP, customer escalations, on-call alerts',
    field: 'critical_messages' as const,
  },
  {
    label: 'Can Wait',
    question: 'What messages can safely wait?',
    placeholder: 'e.g. Project status updates, meeting notes, casual team discussions, automated CI notifications',
    field: 'can_wait' as const,
  },
  {
    label: 'Priority Senders',
    question: 'Any specific senders or channels that should always be high priority?',
    placeholder: 'e.g. My manager @jane, #incidents channel, anyone from the platform team (optional)',
    field: 'priority_senders' as const,
  },
]

const MESSAGES_PER_PAGE = 5

export function ClassifierWizardModal({
  open,
  onOpenChange,
  onApply,
}: ClassifierWizardModalProps) {
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState({
    role: '',
    critical_messages: '',
    can_wait: '',
    priority_senders: '',
  })
  const [editedResult, setEditedResult] = useState<GenerateDefinitionsResponse | null>(null)

  const [allCalibrationMessages, setAllCalibrationMessages] = useState<CalibrationMessage[]>([])
  const [manualMessages, setManualMessages] = useState<CalibrationMessage[]>([])
  const [currentPage, setCurrentPage] = useState(0)
  const [ratings, setRatings] = useState<CalibrationRating[]>([])
  const [manualRatings, setManualRatings] = useState<CalibrationRating[]>([])
  const [showCoverageWarning, setShowCoverageWarning] = useState(false)

  const [showManualSection, setShowManualSection] = useState(false)
  const [manualLinkInput, setManualLinkInput] = useState('')
  const [previewMessage, setPreviewMessage] = useState<CalibrationMessage | null>(null)
  const [previewPriority, setPreviewPriority] = useState<string>('')
  const [previewReasoning, setPreviewReasoning] = useState('')
  const [fetchError, setFetchError] = useState<string | null>(null)

  const generateDefs = useGenerateDefinitions()
  const sampleMessages = useSampleCalibrationMessages()
  const generateFromCalibration = useGenerateDefinitionsFromCalibration()
  const fetchByLink = useFetchMessageByLink()

  const isCalibrationStep = step === 0
  const isQuestionStep = step >= 1 && step <= QUESTIONS_STEPS.length
  const isReviewStep = step === QUESTIONS_STEPS.length + 1
  const currentQuestion = isQuestionStep ? QUESTIONS_STEPS[step - 1] : null
  const isLastQuestion = step === QUESTIONS_STEPS.length

  const totalPages = Math.ceil(allCalibrationMessages.length / MESSAGES_PER_PAGE)
  const paginatedMessages = allCalibrationMessages.slice(
    currentPage * MESSAGES_PER_PAGE,
    (currentPage + 1) * MESSAGES_PER_PAGE
  )

  const allRatings = [...ratings, ...manualRatings]

  const handleNext = () => {
    if (isCalibrationStep) {
      const ratedPriorities = new Set(allRatings.map(r => r.priority))
      const allPriorities = ['p0', 'p1', 'p2', 'p3'] as const
      const missing = allPriorities.filter(p => !ratedPriorities.has(p))

      if (missing.length > 0 && allRatings.length > 0) {
        setShowCoverageWarning(true)
      } else {
        setStep(1)
      }
    } else if (isLastQuestion) {
      handleGenerate()
    } else if (isQuestionStep) {
      setStep(step + 1)
    }
  }

  const handleGenerate = () => {
    setShowCoverageWarning(false)

    if (allRatings.length > 0) {
      generateFromCalibration.mutate(
        {
          ...answers,
          ratings: allRatings,
        },
        {
          onSuccess: (data) => {
            setEditedResult(data)
            setStep(QUESTIONS_STEPS.length + 1)
          },
        }
      )
    } else {
      generateDefs.mutate(answers, {
        onSuccess: (data) => {
          setEditedResult(data)
          setStep(QUESTIONS_STEPS.length + 1)
        },
      })
    }
  }

  const handleFetchMessages = (excludeIds: string[] = []) => {
    sampleMessages.mutate(
      { exclude_message_ids: excludeIds },
      {
        onSuccess: (messages) => {
          if (excludeIds.length === 0) {
            setAllCalibrationMessages(messages)
            setRatings(messages.map(msg => ({
              message_id: msg.message_id,
              message_text: msg.message_text,
              sender_name: msg.sender_name,
              channel_name: msg.channel_name,
              priority: '' as any,
              explanation: '',
            })))
          } else {
            setAllCalibrationMessages(prev => [...prev, ...messages])
            setRatings(prev => [
              ...prev,
              ...messages.map(msg => ({
                message_id: msg.message_id,
                message_text: msg.message_text,
                sender_name: msg.sender_name,
                channel_name: msg.channel_name,
                priority: '' as any,
                explanation: '',
              }))
            ])
          }
        },
      }
    )
  }

  const handleFetchByLink = () => {
    if (!manualLinkInput.trim()) return

    setFetchError(null)
    fetchByLink.mutate(
      { permalink: manualLinkInput.trim() },
      {
        onSuccess: (message) => {
          setPreviewMessage(message)
          setPreviewPriority('')
          setPreviewReasoning('')
        },
        onError: (err: any) => {
          setFetchError(err?.response?.data?.detail || 'Failed to fetch message. Check the link and try again.')
          setPreviewMessage(null)
        },
      }
    )
  }

  const handleAddManualMessage = () => {
    if (!previewMessage || !previewPriority) return

    setManualMessages(prev => [...prev, previewMessage])
    setManualRatings(prev => [...prev, {
      message_id: previewMessage.message_id,
      message_text: previewMessage.message_text,
      sender_name: previewMessage.sender_name,
      channel_name: previewMessage.channel_name,
      priority: previewPriority as any,
      explanation: previewReasoning,
    }])

    setPreviewMessage(null)
    setManualLinkInput('')
    setPreviewPriority('')
    setPreviewReasoning('')
  }

  const handleRemoveManualMessage = (messageId: string) => {
    setManualMessages(prev => prev.filter(m => m.message_id !== messageId))
    setManualRatings(prev => prev.filter(r => r.message_id !== messageId))
  }

  const handleRatingChange = (messageId: string, priority: string, explanation?: string) => {
    setRatings(prev => {
      return prev.map(r => {
        if (r.message_id === messageId) {
          return {
            ...r,
            priority: priority as any,
            explanation: explanation || r.explanation,
          }
        }
        return r
      })
    })
  }

  const handleManualRatingChange = (messageId: string, priority: string, explanation?: string) => {
    setManualRatings(prev => {
      return prev.map(r => {
        if (r.message_id === messageId) {
          return {
            ...r,
            priority: priority as any,
            explanation: explanation || r.explanation,
          }
        }
        return r
      })
    })
  }

  const getRatingForMessage = (messageId: string) => {
    return ratings.find(r => r.message_id === messageId)
  }

  const getManualRatingForMessage = (messageId: string) => {
    return manualRatings.find(r => r.message_id === messageId)
  }

  const handleClose = () => {
    setStep(0)
    setAnswers({ role: '', critical_messages: '', can_wait: '', priority_senders: '' })
    setEditedResult(null)
    setAllCalibrationMessages([])
    setManualMessages([])
    setCurrentPage(0)
    setRatings([])
    setManualRatings([])
    setShowCoverageWarning(false)
    setShowManualSection(false)
    setManualLinkInput('')
    setPreviewMessage(null)
    setPreviewPriority('')
    setPreviewReasoning('')
    setFetchError(null)
    onOpenChange(false)
  }

  const canProceed = isCalibrationStep
    ? allRatings.filter(r => r.priority).length >= 3
    : isQuestionStep && currentQuestion
    ? answers[currentQuestion.field].trim().length > 0
    : false

  const ratedPriorities = new Set(allRatings.filter(r => r.priority).map(r => r.priority))
  const missingPriorities = (['p0', 'p1', 'p2', 'p3'] as const).filter(p => !ratedPriorities.has(p))

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            AI Priority Definition Wizard
          </DialogTitle>
          <DialogDescription>
            Calibrate with real messages and answer questions for personalized priority definitions.
          </DialogDescription>
        </DialogHeader>

        {isReviewStep && editedResult ? (
          <div className="space-y-4">
            <p className="text-sm font-medium">Generated Definitions (editable)</p>
            <div className="space-y-3 text-sm">
              <div>
                <Label className="text-xs font-medium text-muted-foreground">P0 — Urgent</Label>
                <Textarea
                  className="mt-1"
                  rows={2}
                  value={editedResult.p0_definition}
                  onChange={(e) => setEditedResult({ ...editedResult, p0_definition: e.target.value })}
                />
              </div>
              <div>
                <Label className="text-xs font-medium text-muted-foreground">P1 — Important</Label>
                <Textarea
                  className="mt-1"
                  rows={2}
                  value={editedResult.p1_definition}
                  onChange={(e) => setEditedResult({ ...editedResult, p1_definition: e.target.value })}
                />
              </div>
              <div>
                <Label className="text-xs font-medium text-muted-foreground">P2 — Notable</Label>
                <Textarea
                  className="mt-1"
                  rows={2}
                  value={editedResult.p2_definition}
                  onChange={(e) => setEditedResult({ ...editedResult, p2_definition: e.target.value })}
                />
              </div>
              <div>
                <Label className="text-xs font-medium text-muted-foreground">P3 — Low</Label>
                <Textarea
                  className="mt-1"
                  rows={2}
                  value={editedResult.p3_definition}
                  onChange={(e) => setEditedResult({ ...editedResult, p3_definition: e.target.value })}
                />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={handleClose}>
                Cancel
              </Button>
              <Button size="sm" onClick={() => onApply(editedResult)}>
                Apply Definitions
              </Button>
            </div>
          </div>
        ) : isCalibrationStep ? (
          <div className="space-y-4">
            <div className="flex gap-1">
              {[{ label: 'Calibrate' }, ...QUESTIONS_STEPS].map((_, i) => (
                <div
                  key={i}
                  className={`h-1 flex-1 rounded-full ${
                    i <= step ? 'bg-primary' : 'bg-muted'
                  }`}
                />
              ))}
            </div>

            <div className="space-y-2">
              <Label className="text-sm font-medium">Calibrate with Real Messages</Label>
              <p className="text-sm text-muted-foreground">
                Review sample messages from your Slack and rate their priority. This helps Alfred understand your preferences better.
              </p>
            </div>

            {allCalibrationMessages.length === 0 && manualMessages.length === 0 ? (
              <div className="space-y-4">
                <div className="text-center py-4">
                  <Button onClick={() => handleFetchMessages()} disabled={sampleMessages.isPending}>
                    {sampleMessages.isPending ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Fetching Messages...
                      </>
                    ) : (
                      <>
                        <MessageSquare className="h-4 w-4 mr-2" />
                        Fetch Sample Messages
                      </>
                    )}
                  </Button>
                </div>

                <div className="border-t pt-4">
                  <button
                    onClick={() => setShowManualSection(!showManualSection)}
                    className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {showManualSection ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    Or add specific messages by link
                  </button>

                  {showManualSection && (
                    <div className="mt-3 space-y-3">
                      <div className="flex gap-2">
                        <Input
                          placeholder="Paste Slack message link..."
                          value={manualLinkInput}
                          onChange={(e) => setManualLinkInput(e.target.value)}
                          className="flex-1"
                        />
                        <Button
                          onClick={handleFetchByLink}
                          disabled={fetchByLink.isPending || !manualLinkInput.trim()}
                          size="sm"
                        >
                          {fetchByLink.isPending ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Link2 className="h-4 w-4" />
                          )}
                        </Button>
                      </div>

                      {fetchError && (
                        <p className="text-xs text-destructive">{fetchError}</p>
                      )}

                      {previewMessage && (
                        <div className="border rounded-lg p-3 space-y-2 bg-muted/30">
                          <div className="text-xs text-muted-foreground">
                            {previewMessage.channel_type === 'dm' ? '💬' : previewMessage.channel_type === 'private' ? '🔒' : '#'} {previewMessage.channel_name} • {previewMessage.sender_name}
                          </div>
                          <div className="text-sm">{previewMessage.message_text.substring(0, 200)}{previewMessage.message_text.length > 200 ? '...' : ''}</div>

                          <div className="flex gap-2 items-center pt-2">
                            <Select value={previewPriority} onValueChange={setPreviewPriority}>
                              <SelectTrigger className="w-24">
                                <SelectValue placeholder="Priority" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="p0">P0</SelectItem>
                                <SelectItem value="p1">P1</SelectItem>
                                <SelectItem value="p2">P2</SelectItem>
                                <SelectItem value="p3">P3</SelectItem>
                              </SelectContent>
                            </Select>
                            <Button
                              size="sm"
                              onClick={handleAddManualMessage}
                              disabled={!previewPriority}
                            >
                              <Plus className="h-4 w-4 mr-1" />
                              Add to List
                            </Button>
                          </div>

                          <Textarea
                            placeholder="Why this priority? (optional)"
                            className="text-xs h-16"
                            value={previewReasoning}
                            onChange={(e) => setPreviewReasoning(e.target.value)}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="flex justify-center pt-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setStep(1)}
                  >
                    Skip Calibration
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-muted-foreground">Priorities rated:</span>
                  {(['p0', 'p1', 'p2', 'p3'] as const).map(p => (
                    <Badge
                      key={p}
                      variant={ratedPriorities.has(p) ? 'default' : 'outline'}
                      className="text-xs"
                    >
                      {p.toUpperCase()}
                    </Badge>
                  ))}
                </div>

                {showCoverageWarning && missingPriorities.length > 0 && (
                  <div className="rounded-lg bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-900 p-3 text-sm">
                    <p className="font-medium">Missing priorities: {missingPriorities.map(p => p.toUpperCase()).join(', ')}</p>
                    <p className="text-muted-foreground mt-1">
                      For best results, provide at least one example for each priority level.
                    </p>
                    <div className="flex gap-2 mt-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          const existingIds = allCalibrationMessages.map(m => m.message_id)
                          handleFetchMessages(existingIds)
                        }}
                      >
                        Fetch More Messages
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setStep(1)}
                      >
                        Continue to Questions
                      </Button>
                    </div>
                  </div>
                )}

                {manualMessages.length > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-muted-foreground">Manually Added ({manualMessages.length})</span>
                    </div>
                    <div className="space-y-2">
                      {manualMessages.map((msg) => {
                        const rating = getManualRatingForMessage(msg.message_id)
                        return (
                          <div key={msg.message_id} className="border rounded-lg p-3 space-y-2 bg-blue-50/30 dark:bg-blue-950/20">
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex-1">
                                <div className="text-xs text-muted-foreground">
                                  {msg.channel_type === 'dm' ? '💬' : msg.channel_type === 'private' ? '🔒' : '#'} {msg.channel_name} • {msg.sender_name}
                                </div>
                                <div className="text-sm mt-1">{msg.message_text.substring(0, 150)}...</div>
                              </div>
                              <div className="flex items-center gap-2">
                                <Select
                                  value={rating?.priority || ''}
                                  onValueChange={(val) => handleManualRatingChange(msg.message_id, val)}
                                >
                                  <SelectTrigger className="w-20">
                                    <SelectValue placeholder="Rate" />
                                  </SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="p0">P0</SelectItem>
                                    <SelectItem value="p1">P1</SelectItem>
                                    <SelectItem value="p2">P2</SelectItem>
                                    <SelectItem value="p3">P3</SelectItem>
                                  </SelectContent>
                                </Select>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-8 w-8 p-0"
                                  onClick={() => handleRemoveManualMessage(msg.message_id)}
                                >
                                  <X className="h-4 w-4" />
                                </Button>
                              </div>
                            </div>
                            {rating?.priority && (
                              <Textarea
                                placeholder="Why this priority? (optional)"
                                className="text-xs h-16"
                                value={rating?.explanation || ''}
                                onChange={(e) => handleManualRatingChange(msg.message_id, rating.priority, e.target.value)}
                              />
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                {allCalibrationMessages.length > 0 && (
                  <div className="space-y-2">
                    <span className="text-xs font-medium text-muted-foreground">Auto-sampled ({allCalibrationMessages.length})</span>
                    <div className="space-y-3 max-h-64 overflow-y-auto">
                      {paginatedMessages.map((msg) => {
                        const rating = getRatingForMessage(msg.message_id)
                        return (
                          <div key={msg.message_id} className="border rounded-lg p-3 space-y-2">
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex-1">
                                <div className="text-xs text-muted-foreground">
                                  {msg.channel_type === 'dm' ? '💬' : msg.channel_type === 'private' ? '🔒' : '#'} {msg.channel_name} • {msg.sender_name}
                                </div>
                                <div className="text-sm mt-1">{msg.message_text.substring(0, 150)}...</div>
                              </div>
                              <div className="flex-shrink-0">
                                <Select
                                  value={rating?.priority || ''}
                                  onValueChange={(val) => handleRatingChange(msg.message_id, val)}
                                >
                                  <SelectTrigger className="w-20">
                                    <SelectValue placeholder="Rate" />
                                  </SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="p0">P0</SelectItem>
                                    <SelectItem value="p1">P1</SelectItem>
                                    <SelectItem value="p2">P2</SelectItem>
                                    <SelectItem value="p3">P3</SelectItem>
                                  </SelectContent>
                                </Select>
                              </div>
                            </div>
                            {rating?.priority && (
                              <Textarea
                                placeholder="Why this priority? (optional)"
                                className="text-xs h-16"
                                value={rating?.explanation || ''}
                                onChange={(e) => handleRatingChange(msg.message_id, rating.priority, e.target.value)}
                              />
                            )}
                          </div>
                        )
                      })}
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="text-xs text-muted-foreground">
                        {ratings.filter(r => r.priority).length} of {allCalibrationMessages.length} rated
                      </div>
                      {totalPages > 1 && (
                        <div className="flex items-center gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={currentPage === 0}
                            onClick={() => setCurrentPage(prev => prev - 1)}
                          >
                            <ChevronLeft className="h-4 w-4" />
                          </Button>
                          <span className="text-xs">
                            {currentPage + 1}/{totalPages}
                          </span>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={currentPage >= totalPages - 1}
                            onClick={() => setCurrentPage(prev => prev + 1)}
                          >
                            <ChevronRight className="h-4 w-4" />
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                <div className="border-t pt-4">
                  <button
                    onClick={() => setShowManualSection(!showManualSection)}
                    className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {showManualSection ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    Add specific messages by link
                  </button>

                  {showManualSection && (
                    <div className="mt-3 space-y-3">
                      <div className="flex gap-2">
                        <Input
                          placeholder="Paste Slack message link..."
                          value={manualLinkInput}
                          onChange={(e) => setManualLinkInput(e.target.value)}
                          className="flex-1"
                        />
                        <Button
                          onClick={handleFetchByLink}
                          disabled={fetchByLink.isPending || !manualLinkInput.trim()}
                          size="sm"
                        >
                          {fetchByLink.isPending ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Link2 className="h-4 w-4" />
                          )}
                        </Button>
                      </div>

                      {fetchError && (
                        <p className="text-xs text-destructive">{fetchError}</p>
                      )}

                      {previewMessage && (
                        <div className="border rounded-lg p-3 space-y-2 bg-muted/30">
                          <div className="text-xs text-muted-foreground">
                            {previewMessage.channel_type === 'dm' ? '💬' : previewMessage.channel_type === 'private' ? '🔒' : '#'} {previewMessage.channel_name} • {previewMessage.sender_name}
                          </div>
                          <div className="text-sm">{previewMessage.message_text.substring(0, 200)}{previewMessage.message_text.length > 200 ? '...' : ''}</div>

                          <div className="flex gap-2 items-center pt-2">
                            <Select value={previewPriority} onValueChange={setPreviewPriority}>
                              <SelectTrigger className="w-24">
                                <SelectValue placeholder="Priority" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="p0">P0</SelectItem>
                                <SelectItem value="p1">P1</SelectItem>
                                <SelectItem value="p2">P2</SelectItem>
                                <SelectItem value="p3">P3</SelectItem>
                              </SelectContent>
                            </Select>
                            <Button
                              size="sm"
                              onClick={handleAddManualMessage}
                              disabled={!previewPriority}
                            >
                              <Plus className="h-4 w-4 mr-1" />
                              Add to List
                            </Button>
                          </div>

                          <Textarea
                            placeholder="Why this priority? (optional)"
                            className="text-xs h-16"
                            value={previewReasoning}
                            onChange={(e) => setPreviewReasoning(e.target.value)}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="flex justify-between">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const existingIds = allCalibrationMessages.map(m => m.message_id)
                      handleFetchMessages(existingIds)
                    }}
                    disabled={sampleMessages.isPending}
                  >
                    {sampleMessages.isPending ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                        Fetching...
                      </>
                    ) : (
                      'Fetch More Messages'
                    )}
                  </Button>
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setStep(1)}
                    >
                      Skip Calibration
                    </Button>
                    <Button
                      size="sm"
                      disabled={!canProceed}
                      onClick={handleNext}
                    >
                      Continue to Questions
                    </Button>
                  </div>
                </div>
              </>
            )}
          </div>
        ) : currentQuestion ? (
          <div className="space-y-4">
            <div className="flex gap-1">
              {[{ label: 'Calibrate' }, ...QUESTIONS_STEPS].map((_, i) => (
                <div
                  key={i}
                  className={`h-1 flex-1 rounded-full ${
                    i <= step ? 'bg-primary' : 'bg-muted'
                  }`}
                />
              ))}
            </div>

            <div className="space-y-2">
              <Label className="text-sm font-medium">{currentQuestion.question}</Label>
              <div className="flex gap-2">
                <Textarea
                  rows={3}
                  placeholder={currentQuestion.placeholder}
                  value={answers[currentQuestion.field]}
                  onChange={(e) =>
                    setAnswers({ ...answers, [currentQuestion.field]: e.target.value })
                  }
                  autoFocus
                />
              </div>
            </div>

            <div className="flex justify-between">
              <Button
                variant="outline"
                size="sm"
                onClick={() => (step > 1 ? setStep(step - 1) : setStep(0))}
              >
                {step > 1 ? 'Back' : 'Back to Calibration'}
              </Button>
              <div className="flex gap-2">
                {currentQuestion.placeholder && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setAnswers({ ...answers, [currentQuestion.field]: currentQuestion.placeholder.replace('e.g. ', '') })
                    }}
                    disabled={answers[currentQuestion.field] === currentQuestion.placeholder.replace('e.g. ', '')}
                  >
                    <Sparkles className="h-3.5 w-3.5 mr-1.5" />
                    Use Example
                  </Button>
                )}
                <Button
                  size="sm"
                  disabled={!canProceed}
                  onClick={handleNext}
                >
                  {isLastQuestion ? 'Generate Definitions' : 'Next'}
                </Button>
              </div>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
