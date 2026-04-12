import { useState } from 'react'
import { Sparkles, Loader2, MessageSquare } from 'lucide-react'
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
  const [calibrationMessages, setCalibrationMessages] = useState<CalibrationMessage[]>([])
  const [ratings, setRatings] = useState<CalibrationRating[]>([])
  const [showCoverageWarning, setShowCoverageWarning] = useState(false)

  const generateDefs = useGenerateDefinitions()
  const sampleMessages = useSampleCalibrationMessages()
  const generateFromCalibration = useGenerateDefinitionsFromCalibration()

  const isQuestionStep = step >= 0 && step < QUESTIONS_STEPS.length
  const isCalibrationStep = step === QUESTIONS_STEPS.length
  const isReviewStep = step === QUESTIONS_STEPS.length + 1

  const currentQuestion = isQuestionStep ? QUESTIONS_STEPS[step] : null
  const isLastQuestion = step === QUESTIONS_STEPS.length - 1

  const handleNext = () => {
    if (isLastQuestion) {
      // Move to calibration step
      setStep(step + 1)
    } else if (isQuestionStep) {
      setStep(step + 1)
    } else if (isCalibrationStep) {
      // Check coverage
      const ratedPriorities = new Set(ratings.map(r => r.priority))
      const allPriorities = new Set(['p0', 'p1', 'p2', 'p3'])
      const missing = [...allPriorities].filter(p => !ratedPriorities.has(p))

      if (missing.length > 0 && ratings.length > 0) {
        setShowCoverageWarning(true)
      } else {
        // Generate definitions
        handleGenerate()
      }
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
            setStep(step + 1)
          },
        }
      )
    } else {
      // Generate without calibration (traditional)
      generateDefs.mutate(answers, {
        onSuccess: (data) => {
          setResult(data)
          setEditedResult(data)
          setStep(step + 1)
        },
      })
    }
  }

  const handleFetchMessages = () => {
    sampleMessages.mutate(undefined, {
      onSuccess: (messages) => {
        setCalibrationMessages(messages)
        // Initialize empty ratings for each message
        setRatings(messages.map(msg => ({
          message_text: msg.message_text,
          sender_name: msg.sender_name,
          channel_name: msg.channel_name,
          priority: '' as any,
          explanation: '',
        })))
      },
    })
  }

  const handleRatingChange = (index: number, priority: string, explanation?: string) => {
    setRatings(prev => {
      const newRatings = [...prev]
      newRatings[index] = {
        ...newRatings[index],
        priority: priority as any,
        explanation: explanation || newRatings[index].explanation,
      }
      return newRatings
    })
  }

  const handleClose = () => {
    setStep(0)
    setAnswers({ role: '', critical_messages: '', can_wait: '', priority_senders: '' })
    setResult(null)
    setEditedResult(null)
    setCalibrationMessages([])
    setRatings([])
    setShowCoverageWarning(false)
    onOpenChange(false)
  }

  const canProceed = isQuestionStep && currentQuestion
    ? answers[currentQuestion.field].trim().length > 0
    : isCalibrationStep
    ? ratings.filter(r => r.priority).length >= 3
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
            Answer questions and calibrate with real messages for personalized priority definitions.
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
              {[...QUESTIONS_STEPS, { label: 'Calibrate' }].map((_, i) => (
                <div
                  key={i}
                  className={`h-1 flex-1 rounded-full ${
                    i <= step ? 'bg-primary' : 'bg-muted'
                  }`}
                />
              ))}
            </div>

            <div className="space-y-2">
              <Label className="text-sm font-medium">Calibrate with Real Messages (Optional)</Label>
              <p className="text-sm text-muted-foreground">
                Review sample messages from your Slack and rate their priority. This helps Alfred understand your preferences better.
              </p>
            </div>

            {calibrationMessages.length === 0 ? (
              <div className="text-center py-6">
                <Button onClick={handleFetchMessages} disabled={sampleMessages.isPending}>
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
                        onClick={() => handleFetchMessages()}
                      >
                        Fetch More Messages
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleGenerate()}
                      >
                        Continue Anyway
                      </Button>
                    </div>
                  </div>
                )}

                {/* Message cards */}
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  {calibrationMessages.map((msg, idx) => (
                    <div key={idx} className="border rounded-lg p-3 space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1">
                          <div className="text-xs text-muted-foreground">
                            {msg.channel_type === 'private' ? '🔒' : '#'} {msg.channel_name} • {msg.sender_name}
                          </div>
                          <div className="text-sm mt-1">{msg.message_text.substring(0, 150)}...</div>
                        </div>
                        <div className="flex-shrink-0">
                          <Select
                            value={ratings[idx]?.priority || ''}
                            onValueChange={(val) => handleRatingChange(idx, val)}
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
                      {ratings[idx]?.priority && (
                        <Textarea
                          placeholder="Why this priority? (optional)"
                          className="text-xs h-16"
                          value={ratings[idx]?.explanation || ''}
                          onChange={(e) => handleRatingChange(idx, ratings[idx].priority, e.target.value)}
                        />
                      )}
                    </div>
                  ))}
                </div>

                <div className="text-xs text-muted-foreground">
                  {ratings.filter(r => r.priority).length} of {calibrationMessages.length} messages rated
                </div>
              </>
            )}

            <div className="flex justify-between">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setStep(step - 1)}
              >
                Back
              </Button>
              <div className="flex gap-2">
                {calibrationMessages.length > 0 && ratings.filter(r => r.priority).length === 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleGenerate()}
                  >
                    Skip Calibration
                  </Button>
                )}
                <Button
                  size="sm"
                  disabled={!canProceed || generateFromCalibration.isPending || generateDefs.isPending}
                  onClick={handleNext}
                >
                  {generateFromCalibration.isPending || generateDefs.isPending ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                      Generating...
                    </>
                  ) : (
                    'Generate Definitions'
                  )}
                </Button>
              </div>
            </div>
          </div>
        ) : currentQuestion ? (
          <div className="space-y-4">
            {/* Step indicator */}
            <div className="flex gap-1">
              {QUESTIONS_STEPS.map((_, i) => (
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

            <div className="flex justify-between">
              <Button
                variant="outline"
                size="sm"
                onClick={() => (step > 0 ? setStep(step - 1) : handleClose())}
              >
                {step > 0 ? 'Back' : 'Cancel'}
              </Button>
              <Button
                size="sm"
                disabled={!canProceed}
                onClick={handleNext}
              >
                {isLastQuestion ? 'Next: Calibrate' : 'Next'}
              </Button>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}