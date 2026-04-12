import { useState } from 'react'
import { Sparkles, Loader2, MessageSquare, ChevronLeft, ChevronRight } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useGenerateDefinitions, useSampleCalibrationMessages, useGenerateDefinitionsFromCalibration } from '@/hooks/useTriage'
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
  const [result, setResult] = useState<GenerateDefinitionsResponse | null>(null)
  const [editedResult, setEditedResult] = useState<GenerateDefinitionsResponse | null>(null)

  // Calibration state
  const [allCalibrationMessages, setAllCalibrationMessages] = useState<CalibrationMessage[]>([])
  const [currentPage, setCurrentPage] = useState(0)
  const [ratings, setRatings] = useState<CalibrationRating[]>([])
  const [showCoverageWarning, setShowCoverageWarning] = useState(false)

  const generateDefs = useGenerateDefinitions()
  const sampleMessages = useSampleCalibrationMessages()
  const generateFromCalibration = useGenerateDefinitionsFromCalibration()

  // Step 0: Calibration (messages first)
  // Steps 1-4: Questions
  // Step 5: Review
  const isCalibrationStep = step === 0
  const isQuestionStep = step >= 1 && step <= QUESTIONS_STEPS.length
  const isReviewStep = step === QUESTIONS_STEPS.length + 1
  const currentQuestion = isQuestionStep ? QUESTIONS_STEPS[step - 1] : null
  const isLastQuestion = step === QUESTIONS_STEPS.length

  // Pagination for calibration messages
  const totalPages = Math.ceil(allCalibrationMessages.length / MESSAGES_PER_PAGE)
  const paginatedMessages = allCalibrationMessages.slice(
    currentPage * MESSAGES_PER_PAGE,
    (currentPage + 1) * MESSAGES_PER_PAGE
  )

  const handleNext = () => {
    if (isCalibrationStep) {
      // Check coverage
      const ratedPriorities = new Set(ratings.map(r => r.priority))
      const allPriorities = new Set(['p0', 'p1', 'p2', 'p3'])
      const missing = [...allPriorities].filter(p => !ratedPriorities.has(p))

      if (missing.length > 0 && ratings.length > 0) {
        setShowCoverageWarning(true)
      } else {
        // Move to questions
        setStep(1)
      }
    } else if (isLastQuestion) {
      // Generate definitions
      handleGenerate()
    } else if (isQuestionStep) {
      setStep(step + 1)
    }
  }

  const handleGenerate = () => {
    setShowCoverageWarning(false)

    if (ratings.length > 0) {
      // Generate from calibration
      generateFromCalibration.mutate(
        {
          ...answers,
          ratings,
        },
        {
          onSuccess: (data) => {
            setResult(data)
            setEditedResult(data)
            setStep(QUESTIONS_STEPS.length + 1)
          },
        }
      )
    } else {
      // Generate without calibration (traditional)
      generateDefs.mutate(answers, {
        onSuccess: (data) => {
          setResult(data)
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
            // First fetch - set all messages
            setAllCalibrationMessages(messages)
            // Initialize empty ratings for each message
            setRatings(messages.map(msg => ({
              message_id: msg.message_id,
              message_text: msg.message_text,
              sender_name: msg.sender_name,
              channel_name: msg.channel_name,
              priority: '' as any,
              explanation: '',
            })))
          } else {
            // Subsequent fetch - append messages
            setAllCalibrationMessages(prev => [...prev, ...messages])
            // Append new ratings
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

  const getRatingForMessage = (messageId: string) => {
    return ratings.find(r => r.message_id === messageId)
  }

  const handleClose = () => {
    setStep(0)
    setAnswers({ role: '', critical_messages: '', can_wait: '', priority_senders: '' })
    setResult(null)
    setEditedResult(null)
    setAllCalibrationMessages([])
    setCurrentPage(0)
    setRatings([])
    setShowCoverageWarning(false)
    onOpenChange(false)
  }

  const canProceed = isCalibrationStep
    ? ratings.filter(r => r.priority).length >= 3
    : isQuestionStep && currentQuestion
    ? answers[currentQuestion.field].trim().length > 0
    : false

  const ratedPriorities = new Set(ratings.filter(r => r.priority).map(r => r.priority))
  const missingPriorities = ['p0', 'p1', 'p2', 'p3'].filter(p => !ratedPriorities.has(p))

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
            {/* Step indicator */}
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
                Review sample messages from your Slack (DMs, public and private channels) and rate their priority. This helps Alfred understand your preferences better.
              </p>
            </div>

            {allCalibrationMessages.length === 0 ? (
              <div className="text-center py-6">
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
            ) : (
              <>
                {/* Coverage status */}
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-muted-foreground">Priorities rated:</span>
                  {['p0', 'p1', 'p2', 'p3'].map(p => (
                    <Badge
                      key={p}
                      variant={ratedPriorities.has(p) ? 'default' : 'outline'}
                      className="text-xs"
                    >
                      {p.toUpperCase()}
                    </Badge>
                  ))}
                </div>

                {/* Coverage warning */}
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

                {/* Message cards with pagination */}
                <div className="space-y-3 max-h-96 overflow-y-auto">
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

                {/* Pagination controls */}
                <div className="flex items-center justify-between">
                  <div className="text-xs text-muted-foreground">
                    {ratings.filter(r => r.priority).length} of {allCalibrationMessages.length} messages rated
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
                        Page {currentPage + 1} of {totalPages}
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
                    {ratings.filter(r => r.priority).length === 0 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setStep(1)}
                      >
                        Skip Calibration
                      </Button>
                    )}
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
            {/* Step indicator */}
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