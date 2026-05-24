import { useState } from 'react'
import { Sparkles, Loader2, Link2, Plus, X, Check } from 'lucide-react'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  useGenerateWizardGoals,
  useGenerateWizardQuestions,
  useGenerateWizardDefinitions,
  useFetchWizardMessages,
} from '@/hooks/useTriage'
import type {
  WizardQuestion,
  WizardGoal,
  MessageTypeSuggestion,
  FetchedMessage,
  WizardDefinitionResponse,
} from '@/types'
import { PRIORITY_LABELS } from '@/types'

interface ClassifierWizardModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onApply: (
    definitions: {
      p0_definition: string
      p1_definition: string
      p2_definition: string
      p3_definition: string
    },
    messageTypes: MessageTypeSuggestion[]
  ) => void
}

const PRIORITY_OPTIONS = ['p0', 'p1', 'p2', 'p3'] as const

export function ClassifierWizardModal({
  open,
  onOpenChange,
  onApply,
}: ClassifierWizardModalProps) {
  const [step, setStep] = useState(1)

  const [role, setRole] = useState('')

  const [generatedGoals, setGeneratedGoals] = useState<WizardGoal[]>([])
  const [selectedGoalIds, setSelectedGoalIds] = useState<Set<string>>(new Set())
  const [customGoals, setCustomGoals] = useState<WizardGoal[]>([])
  const [customGoalInput, setCustomGoalInput] = useState('')

  const [wizardQuestions, setWizardQuestions] = useState<WizardQuestion[]>([])
  const [questionResponses, setQuestionResponses] = useState<Record<string, string>>({})

  const [messageTypes, setMessageTypes] = useState<MessageTypeSuggestion[]>([])
  const [selectedMessageTypes, setSelectedMessageTypes] = useState<Set<number>>(new Set())

  const [slackLinks, setSlackLinks] = useState<string[]>([''])
  const [fetchedMessages, setFetchedMessages] = useState<FetchedMessage[]>([])
  const [messagePriorities, setMessagePriorities] = useState<Record<string, string>>({})

  const [editedResult, setEditedResult] = useState<WizardDefinitionResponse | null>(null)

  const generateGoals = useGenerateWizardGoals()
  const generateQuestions = useGenerateWizardQuestions()
  const generateDefinitions = useGenerateWizardDefinitions()
  const fetchMessages = useFetchWizardMessages()

  const allGoals = [...generatedGoals, ...customGoals]
  const selectedGoals = allGoals.filter(g => selectedGoalIds.has(g.id))

  const handleGoalToggle = (goalId: string) => {
    setSelectedGoalIds(prev => {
      const next = new Set(prev)
      if (next.has(goalId)) {
        next.delete(goalId)
      } else {
        next.add(goalId)
      }
      return next
    })
  }

  const handleAddCustomGoal = () => {
    if (!customGoalInput.trim()) return
    const newGoal: WizardGoal = {
      id: `custom-${Date.now()}`,
      label: customGoalInput.trim(),
    }
    setCustomGoals(prev => [...prev, newGoal])
    setSelectedGoalIds(prev => new Set([...prev, newGoal.id]))
    setCustomGoalInput('')
  }

  const handleRemoveCustomGoal = (goalId: string) => {
    setCustomGoals(prev => prev.filter(g => g.id !== goalId))
    setSelectedGoalIds(prev => {
      const next = new Set(prev)
      next.delete(goalId)
      return next
    })
  }

  const handleNextStep1 = () => {
    if (!role.trim()) return

    generateGoals.mutate(
      { role },
      {
        onSuccess: (data) => {
          setGeneratedGoals(data.goals)
          setSelectedGoalIds(new Set(data.goals.map(g => g.id)))
          setStep(2)
        },
      }
    )
  }

  const handleNextStep2 = () => {
    if (selectedGoalIds.size === 0) return

    const goalLabels = selectedGoals.map(g => g.label)

    generateQuestions.mutate(
      { role, goals: goalLabels },
      {
        onSuccess: (data) => {
          setWizardQuestions(data.questions)
          const initialResponses: Record<string, string> = {}
          data.questions.forEach(q => {
            initialResponses[q.question] = q.options[0] || ''
          })
          setQuestionResponses(initialResponses)
          setStep(3)
        },
      }
    )
  }

  const handleNextStep3 = () => {
    generateDefinitions.mutate(
      {
        role,
        goals: selectedGoals.map(g => g.label),
        question_responses: questionResponses,
        message_types: [],
        example_messages: null,
      },
      {
        onSuccess: (data) => {
          setMessageTypes(data.suggested_message_types)
          setSelectedMessageTypes(new Set(data.suggested_message_types.map((_, i) => i)))
          setEditedResult(data)
          setStep(4)
        },
      }
    )
  }

  const handleNextStep4 = () => {
    setStep(5)
  }

  const handleSkipCalibration = () => {
    setStep(6)
  }

  const handleGenerateWithCalibration = () => {
    const selectedTypes = messageTypes
      .filter((_, idx) => selectedMessageTypes.has(idx))
      .map(t => ({ type_name: t.type_name, type_definition: t.type_definition }))

    const examples = fetchedMessages
      .filter(m => messagePriorities[m.slack_link])
      .map(m => ({
        text: m.text,
        priority: messagePriorities[m.slack_link],
      }))

    generateDefinitions.mutate(
      {
        role,
        goals: selectedGoals.map(g => g.label),
        question_responses: questionResponses,
        message_types: selectedTypes,
        example_messages: examples.length > 0 ? examples : null,
      },
      {
        onSuccess: (data) => {
          setEditedResult(data)
          setStep(6)
        },
      }
    )
  }

  const handleFetchMessages = () => {
    const validLinks = slackLinks.filter(l => l.trim().length > 0)
    if (validLinks.length === 0) return

    fetchMessages.mutate(
      { slack_links: validLinks },
      {
        onSuccess: (data) => {
          setFetchedMessages(data.messages)
        },
      }
    )
  }

  const handleAddSlackLink = () => {
    setSlackLinks([...slackLinks, ''])
  }

  const handleRemoveSlackLink = (index: number) => {
    setSlackLinks(slackLinks.filter((_, i) => i !== index))
  }

  const handleSlackLinkChange = (index: number, value: string) => {
    setSlackLinks(slackLinks.map((l, i) => (i === index ? value : l)))
  }

  const handleClose = () => {
    setStep(1)
    setRole('')
    setGeneratedGoals([])
    setSelectedGoalIds(new Set())
    setCustomGoals([])
    setCustomGoalInput('')
    setWizardQuestions([])
    setQuestionResponses({})
    setMessageTypes([])
    setSelectedMessageTypes(new Set())
    setSlackLinks([''])
    setFetchedMessages([])
    setMessagePriorities({})
    setEditedResult(null)
    onOpenChange(false)
  }

  const handleApply = () => {
    if (!editedResult) return

    const selectedTypes = messageTypes.filter((_, idx) => selectedMessageTypes.has(idx))

    onApply(
      {
        p0_definition: editedResult.p0_definition,
        p1_definition: editedResult.p1_definition,
        p2_definition: editedResult.p2_definition,
        p3_definition: editedResult.p3_definition,
      },
      selectedTypes
    )
    handleClose()
  }

  const renderStepIndicator = () => (
    <div className="flex gap-1 mb-4">
      {[1, 2, 3, 4, 5, 6].map((s) => (
        <div
          key={s}
          className={`h-1 flex-1 rounded-full ${s <= step ? 'bg-primary' : 'bg-muted'}`}
        />
      ))}
    </div>
  )

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            AI Priority Definition Wizard
          </DialogTitle>
          <DialogDescription>
            Answer a few questions to generate personalized priority definitions.
          </DialogDescription>
        </DialogHeader>

        {step === 1 && (
          <div className="space-y-4">
            {renderStepIndicator()}

            <div className="space-y-2">
              <Label className="text-sm font-medium">What is your role?</Label>
              <Textarea
                placeholder="e.g. Engineering manager at a startup, overseeing 3 teams. I handle on-call rotations and weekly team syncs."
                value={role}
                onChange={(e) => setRole(e.target.value)}
                rows={3}
                autoFocus
              />
              <p className="text-xs text-muted-foreground">
                Be specific about your responsibilities and team size.
              </p>
            </div>

            <div className="flex justify-end">
              <Button
                onClick={handleNextStep1}
                disabled={!role.trim() || generateGoals.isPending}
              >
                {generateGoals.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Generating Goals...
                  </>
                ) : (
                  'Next'
                )}
              </Button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            {renderStepIndicator()}

            <div className="space-y-2">
              <Label className="text-sm font-medium">What are your goals? (select all that apply)</Label>
              <p className="text-xs text-muted-foreground mb-3">
                Based on your role: "{role}"
              </p>

              <div className="space-y-2">
                {allGoals.map((goal) => (
                  <button
                    key={goal.id}
                    type="button"
                    onClick={() => handleGoalToggle(goal.id)}
                    className={`flex items-center justify-between rounded-md border p-3 w-full text-left cursor-pointer transition-colors ${
                      selectedGoalIds.has(goal.id)
                        ? 'bg-primary/10 border-primary'
                        : 'hover:bg-muted/50'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      {selectedGoalIds.has(goal.id) ? (
                        <Check className="h-4 w-4 text-primary shrink-0" />
                      ) : (
                        <div className="h-4 w-4 border rounded shrink-0" />
                      )}
                      <Label className="text-sm cursor-pointer">
                        {goal.label}
                      </Label>
                    </div>
                    {goal.id.startsWith('custom-') && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleRemoveCustomGoal(goal.id)
                        }}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    )}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex gap-2">
              <Input
                placeholder="Add a custom goal..."
                value={customGoalInput}
                onChange={(e) => setCustomGoalInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleAddCustomGoal()
                  }
                }}
              />
              <Button
                variant="outline"
                onClick={handleAddCustomGoal}
                disabled={!customGoalInput.trim()}
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex justify-between">
              <Button variant="ghost" onClick={() => setStep(1)}>
                Back
              </Button>
              <Button
                onClick={handleNextStep2}
                disabled={selectedGoalIds.size === 0 || generateQuestions.isPending}
              >
                {generateQuestions.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Generating Questions...
                  </>
                ) : (
                  'Next'
                )}
              </Button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            {renderStepIndicator()}

            <div className="space-y-4">
              <Label className="text-sm font-medium">Answer these questions:</Label>

              {wizardQuestions.map((q, idx) => (
                <div key={idx} className="space-y-2">
                  <Label className="text-sm">{q.question}</Label>
                  <Select
                    value={questionResponses[q.question] || ''}
                    onValueChange={(val) =>
                      setQuestionResponses(prev => ({ ...prev, [q.question]: val }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select an option" />
                    </SelectTrigger>
                    <SelectContent>
                      {q.options.map((opt, optIdx) => (
                        <SelectItem key={optIdx} value={opt}>
                          {opt}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </div>

            <div className="flex justify-between">
              <Button variant="ghost" onClick={() => setStep(2)}>
                Back
              </Button>
              <Button onClick={handleNextStep3} disabled={generateDefinitions.isPending}>
                {generateDefinitions.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Generating...
                  </>
                ) : (
                  'Next'
                )}
              </Button>
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-4">
            {renderStepIndicator()}

            <div className="space-y-2">
              <Label className="text-sm font-medium">Suggested Message Types</Label>
              <p className="text-xs text-muted-foreground mb-3">
                Select the types that are relevant to you:
              </p>

              <div className="space-y-2">
                {messageTypes.map((type, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => {
                      setSelectedMessageTypes(prev => {
                        const next = new Set(prev)
                        if (next.has(idx)) {
                          next.delete(idx)
                        } else {
                          next.add(idx)
                        }
                        return next
                      })
                    }}
                    className={`flex items-start space-x-3 rounded-md border p-3 w-full text-left cursor-pointer transition-colors ${
                      selectedMessageTypes.has(idx)
                        ? 'bg-primary/10 border-primary'
                        : 'hover:bg-muted/50'
                    }`}
                  >
                    <div className="mt-0.5">
                      {selectedMessageTypes.has(idx) ? (
                        <Check className="h-4 w-4 text-primary" />
                      ) : (
                        <div className="h-4 w-4 border rounded" />
                      )}
                    </div>
                    <div>
                      <Label className="text-sm font-medium cursor-pointer">
                        {type.type_name}
                      </Label>
                      <p className="text-xs text-muted-foreground">
                        {type.type_definition}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex justify-between">
              <Button variant="ghost" onClick={() => setStep(3)}>
                Back
              </Button>
              <Button onClick={handleNextStep4}>
                Next: Calibrate (Optional)
              </Button>
            </div>
          </div>
        )}

        {step === 5 && (
          <div className="space-y-4">
            {renderStepIndicator()}

            <div className="space-y-2">
              <Label className="text-sm font-medium flex items-center gap-2">
                <Link2 className="h-4 w-4" />
                Calibrate with Examples (Optional)
              </Label>
              <p className="text-xs text-muted-foreground mb-3">
                Paste Slack message links to help refine the priority definitions.
              </p>

              {slackLinks.map((link, idx) => (
                <div key={idx} className="flex gap-2">
                  <Input
                    placeholder="https://your-workspace.slack.com/archives/..."
                    value={link}
                    onChange={(e) => handleSlackLinkChange(idx, e.target.value)}
                  />
                  {slackLinks.length > 1 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveSlackLink(idx)}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              ))}

              <Button variant="outline" size="sm" onClick={handleAddSlackLink} className="mt-2">
                <Plus className="h-4 w-4 mr-1" />
                Add Another Link
              </Button>
            </div>

            <Button
              onClick={handleFetchMessages}
              disabled={slackLinks.every(l => !l.trim()) || fetchMessages.isPending}
            >
              {fetchMessages.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Fetching...
                </>
              ) : (
                <>
                  <Link2 className="h-4 w-4 mr-2" />
                  Fetch Messages
                </>
              )}
            </Button>

            {fetchMessages.isPending && (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Fetching messages...
              </div>
            )}

            {fetchedMessages.length > 0 && (
              <div className="space-y-3">
                <Label className="text-sm font-medium">Label these messages:</Label>
                {fetchedMessages.map((msg) => (
                  <div key={msg.slack_link} className="border rounded-md p-3 space-y-2">
                    <p className="text-sm">{msg.text}</p>
                    <Select
                      value={messagePriorities[msg.slack_link] || ''}
                      onValueChange={(val) =>
                        setMessagePriorities(prev => ({ ...prev, [msg.slack_link]: val }))
                      }
                    >
                      <SelectTrigger className="h-8">
                        <SelectValue placeholder="Select priority" />
                      </SelectTrigger>
                      <SelectContent>
                        {PRIORITY_OPTIONS.map((p) => (
                          <SelectItem key={p} value={p}>
                            {PRIORITY_LABELS[p]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            )}

            <div className="flex justify-between">
              <Button variant="ghost" onClick={() => setStep(4)}>
                Back
              </Button>
              <div className="flex gap-2">
                <Button variant="outline" onClick={handleSkipCalibration}>
                  Skip
                </Button>
                <Button
                  onClick={handleGenerateWithCalibration}
                  disabled={generateDefinitions.isPending}
                >
                  {generateDefinitions.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Refining...
                    </>
                  ) : fetchedMessages.length > 0 ? (
                    'Apply Calibration'
                  ) : (
                    'Generate Definitions'
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}

        {step === 6 && editedResult && (
          <div className="space-y-4">
            {renderStepIndicator()}

            <div className="space-y-3">
              <Label className="text-sm font-medium">Review & Edit Definitions</Label>

              {PRIORITY_OPTIONS.map((p) => (
                <div key={p} className="space-y-1">
                  <Label className="text-xs font-medium text-muted-foreground">
                    {PRIORITY_LABELS[p]}
                  </Label>
                  <Textarea
                    value={editedResult[`${p}_definition` as keyof WizardDefinitionResponse] as string}
                    onChange={(e) =>
                      setEditedResult({
                        ...editedResult,
                        [`${p}_definition`]: e.target.value,
                      })
                    }
                    rows={2}
                  />
                </div>
              ))}
            </div>

            <div className="flex justify-between">
              <Button variant="ghost" onClick={() => setStep(5)}>
                Back
              </Button>
              <Button onClick={handleApply}>
                <Check className="h-4 w-4 mr-2" />
                Apply Definitions
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
