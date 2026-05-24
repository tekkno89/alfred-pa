import { useState } from 'react'
import { Sparkles, Loader2, Link2, Plus, X, Check, RefreshCw } from 'lucide-react'
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
import {
  useGenerateWizardQuestions,
  useGenerateWizardDefinitions,
  useFetchWizardMessages,
} from '@/hooks/useTriage'
import type {
  WizardQuestion,
  MessageTypeSuggestion,
  FetchedMessage,
  WizardDefinitionResponse,
} from '@/types'
import { PRIORITY_LABELS } from '@/types'

interface ClassifierWizardModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onApply: (definitions: { p0_definition: string; p1_definition: string; p2_definition: string; p3_definition: string }) => void
}

const GOAL_OPTIONS = [
  { id: 'incidents', label: 'Stay on top of production incidents' },
  { id: 'noise', label: 'Reduce noise from automated messages' },
  { id: 'directs', label: 'Never miss direct messages from my team' },
  { id: 'deadlines', label: 'Track deadlines and time-sensitive requests' },
  { id: 'fyi', label: 'Keep up with FYI announcements' },
]

const PRIORITY_OPTIONS = ['p0', 'p1', 'p2', 'p3'] as const

export function ClassifierWizardModal({
  open,
  onOpenChange,
  onApply,
}: ClassifierWizardModalProps) {
  const [step, setStep] = useState(1)
  
  const [role, setRole] = useState('')
  const [selectedGoals, setSelectedGoals] = useState<string[]>([])
  
  const [wizardQuestions, setWizardQuestions] = useState<WizardQuestion[]>([])
  const [questionResponses, setQuestionResponses] = useState<Record<string, string>>({})
  
  const [messageTypes, setMessageTypes] = useState<MessageTypeSuggestion[]>([])
  const [selectedMessageTypes, setSelectedMessageTypes] = useState<Set<number>>(new Set())
  
  const [slackLinks, setSlackLinks] = useState<string[]>([''])
  const [fetchedMessages, setFetchedMessages] = useState<FetchedMessage[]>([])
  const [messagePriorities, setMessagePriorities] = useState<Record<string, string>>({})
  
  const [editedResult, setEditedResult] = useState<WizardDefinitionResponse | null>(null)

  const generateQuestions = useGenerateWizardQuestions()
  const generateDefinitions = useGenerateWizardDefinitions()
  const fetchMessages = useFetchWizardMessages()

  const handleGoalToggle = (goalId: string) => {
    setSelectedGoals(prev =>
      prev.includes(goalId)
        ? prev.filter(g => g !== goalId)
        : [...prev, goalId]
    )
  }

  const handleNextStep1 = () => {
    if (!role.trim()) return
    
    generateQuestions.mutate(
      { role, goals: selectedGoals },
      {
        onSuccess: (data) => {
          setWizardQuestions(data.questions)
          const initialResponses: Record<string, string> = {}
          data.questions.forEach(q => {
            initialResponses[q.question] = q.options[0] || ''
          })
          setQuestionResponses(initialResponses)
          setStep(2)
        },
      }
    )
  }

  const handleNextStep2 = () => {
    generateDefinitions.mutate(
      {
        role,
        goals: selectedGoals,
        question_responses: questionResponses,
        message_types: [],
        example_messages: null,
      },
      {
        onSuccess: (data) => {
          setMessageTypes(data.suggested_message_types)
          setSelectedMessageTypes(new Set(data.suggested_message_types.map((_, i) => i)))
          setEditedResult(data)
          setStep(3)
        },
      }
    )
  }

  const handleSkipCalibration = () => {
    setStep(5)
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
        goals: selectedGoals,
        question_responses: questionResponses,
        message_types: selectedTypes,
        example_messages: examples.length > 0 ? examples : null,
      },
      {
        onSuccess: (data) => {
          setEditedResult(data)
          setStep(5)
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
    setSelectedGoals([])
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
    onApply({
      p0_definition: editedResult.p0_definition,
      p1_definition: editedResult.p1_definition,
      p2_definition: editedResult.p2_definition,
      p3_definition: editedResult.p3_definition,
    })
    handleClose()
  }

  const renderStepIndicator = () => (
    <div className="flex gap-1 mb-4">
      {[1, 2, 3, 4, 5].map((s) => (
        <div
          key={s}
          className={`h-1 flex-1 rounded-full ${
            s <= step ? 'bg-primary' : 'bg-muted'
          }`}
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
              <Input
                placeholder="e.g. Engineering manager at a startup, overseeing 3 teams"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                autoFocus
              />
            </div>

            <div className="space-y-2">
              <Label className="text-sm font-medium">What are your goals? (select all that apply)</Label>
              <div className="space-y-2">
                {GOAL_OPTIONS.map((goal) => (
                  <button
                    key={goal.id}
                    type="button"
                    onClick={() => handleGoalToggle(goal.id)}
                    className={`flex items-start space-x-3 rounded-md border p-3 w-full text-left cursor-pointer transition-colors ${
                      selectedGoals.includes(goal.id)
                        ? 'bg-primary/10 border-primary'
                        : 'hover:bg-muted/50'
                    }`}
                  >
                    <div className="mt-0.5">
                      {selectedGoals.includes(goal.id) ? (
                        <Check className="h-4 w-4 text-primary" />
                      ) : (
                        <div className="h-4 w-4 border rounded" />
                      )}
                    </div>
                    <Label className="text-sm cursor-pointer">
                      {goal.label}
                    </Label>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex justify-end">
              <Button
                onClick={handleNextStep1}
                disabled={!role.trim() || generateQuestions.isPending}
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

        {step === 2 && (
          <div className="space-y-4">
            {renderStepIndicator()}
            
            <div className="space-y-4">
              <Label className="text-sm font-medium">Answer the following questions:</Label>
              {wizardQuestions.length === 0 ? (
                <div className="text-sm text-muted-foreground">Loading questions...</div>
              ) : (
                wizardQuestions.map((q, idx) => (
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
                ))
              )}
            </div>

            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep(1)}>
                Back
              </Button>
              <Button onClick={handleNextStep2} disabled={generateDefinitions.isPending}>
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

        {step === 3 && (
          <div className="space-y-4">
            {renderStepIndicator()}
            
            <div className="space-y-2">
              <Label className="text-sm font-medium">Suggested Message Types</Label>
              <p className="text-sm text-muted-foreground">
                We've identified message types relevant to your role. Select the ones you want to track.
              </p>
            </div>

            {messageTypes.length === 0 ? (
              <div className="text-sm text-muted-foreground">
                No suggestions available.
              </div>
            ) : (
              <div className="space-y-2">
                {messageTypes.map((mt, idx) => (
                  <div
                    key={idx}
                    className="flex items-start space-x-3 rounded-md border p-3 cursor-pointer hover:bg-muted/50"
                    onClick={() => {
                      const newSelected = new Set(selectedMessageTypes)
                      if (newSelected.has(idx)) {
                        newSelected.delete(idx)
                      } else {
                        newSelected.add(idx)
                      }
                      setSelectedMessageTypes(newSelected)
                    }}
                  >
                    <div className="mt-0.5">
                      {selectedMessageTypes.has(idx) ? (
                        <Check className="h-4 w-4 text-primary" />
                      ) : (
                        <div className="h-4 w-4 border rounded" />
                      )}
                    </div>
                    <div className="flex-1">
                      <div className="font-medium text-sm">{mt.type_name}</div>
                      <div className="text-xs text-muted-foreground">{mt.type_definition}</div>
                    </div>
                    {mt.confidence > 0.8 && (
                      <Badge variant="secondary" className="text-xs">High confidence</Badge>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep(2)}>
                Back
              </Button>
              <div className="flex gap-2">
                <Button variant="outline" onClick={handleSkipCalibration}>
                  Skip Calibration
                </Button>
                <Button onClick={() => setStep(4)}>
                  Add Calibration Examples
                </Button>
              </div>
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-4">
            {renderStepIndicator()}
            
            <div className="space-y-2">
              <Label className="text-sm font-medium">Calibrate with Example Messages (optional)</Label>
              <p className="text-sm text-muted-foreground">
                Paste Slack message links to provide examples. This helps improve classification accuracy.
              </p>
            </div>

            <div className="space-y-2">
              {slackLinks.map((link, idx) => (
                <div key={idx} className="flex gap-2">
                  <Input
                    placeholder="https://your-workspace.slack.com/archives/..."
                    value={link}
                    onChange={(e) => handleSlackLinkChange(idx, e.target.value)}
                    className="flex-1"
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
              <Button variant="outline" size="sm" onClick={handleAddSlackLink}>
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

            {fetchedMessages.length > 0 && (
              <div className="space-y-2">
                <Label className="text-sm font-medium">Rate these messages:</Label>
                {fetchedMessages.map((msg) => (
                  <div key={msg.slack_link} className="border rounded-lg p-3 space-y-2">
                    <div className="text-xs text-muted-foreground">
                      {msg.sender_name} in {msg.channel_name}
                    </div>
                    <div className="text-sm">{msg.text.substring(0, 200)}{msg.text.length > 200 ? '...' : ''}</div>
                    <Select
                      value={messagePriorities[msg.slack_link] || ''}
                      onValueChange={(val) =>
                        setMessagePriorities(prev => ({ ...prev, [msg.slack_link]: val }))
                      }
                    >
                      <SelectTrigger className="w-52">
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
              <Button variant="outline" onClick={() => setStep(3)}>
                Back
              </Button>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setStep(5)}>
                  Skip
                </Button>
                <Button
                  onClick={handleGenerateWithCalibration}
                  disabled={generateDefinitions.isPending}
                >
                  {generateDefinitions.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Generating...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="h-4 w-4 mr-2" />
                      Regenerate with Examples
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}

        {step === 5 && editedResult && (
          <div className="space-y-4">
            {renderStepIndicator()}
            
            <p className="text-sm font-medium">Review & Edit Definitions</p>
            
            <div className="space-y-3 text-sm">
              <div>
                <Label className="text-xs font-medium text-muted-foreground">{PRIORITY_LABELS.p0}</Label>
                <Textarea
                  className="mt-1"
                  rows={2}
                  value={editedResult.p0_definition}
                  onChange={(e) => setEditedResult({ ...editedResult, p0_definition: e.target.value })}
                />
              </div>
              <div>
                <Label className="text-xs font-medium text-muted-foreground">{PRIORITY_LABELS.p1}</Label>
                <Textarea
                  className="mt-1"
                  rows={2}
                  value={editedResult.p1_definition}
                  onChange={(e) => setEditedResult({ ...editedResult, p1_definition: e.target.value })}
                />
              </div>
              <div>
                <Label className="text-xs font-medium text-muted-foreground">{PRIORITY_LABELS.p2}</Label>
                <Textarea
                  className="mt-1"
                  rows={2}
                  value={editedResult.p2_definition}
                  onChange={(e) => setEditedResult({ ...editedResult, p2_definition: e.target.value })}
                />
              </div>
              <div>
                <Label className="text-xs font-medium text-muted-foreground">{PRIORITY_LABELS.p3}</Label>
                <Textarea
                  className="mt-1"
                  rows={2}
                  value={editedResult.p3_definition}
                  onChange={(e) => setEditedResult({ ...editedResult, p3_definition: e.target.value })}
                />
              </div>
            </div>

            {editedResult.suggested_message_types.length > 0 && (
              <div className="space-y-2">
                <Label className="text-sm font-medium">Suggested Message Types</Label>
                <div className="flex flex-wrap gap-2">
                  {editedResult.suggested_message_types.map((mt, idx) => (
                    <Badge key={idx} variant="secondary">
                      {mt.type_name}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={handleClose}>
                Cancel
              </Button>
              <Button size="sm" onClick={handleApply}>
                Apply Definitions
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
