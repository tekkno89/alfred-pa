import { useState } from 'react'
import { Sparkles, Loader2 } from 'lucide-react'
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
import { useGenerateDefinitions } from '@/hooks/useTriage'
import type { GenerateDefinitionsResponse } from '@/types'

interface ClassifierWizardModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onApply: (definitions: GenerateDefinitionsResponse) => void
}

const STEPS = [
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
  const generateDefs = useGenerateDefinitions()

  const currentStep = STEPS[step]
  const isLastStep = step === STEPS.length - 1
  const isReviewStep = step === STEPS.length

  const handleNext = () => {
    if (isLastStep) {
      // Generate definitions
      generateDefs.mutate(answers, {
        onSuccess: (data) => {
          setResult(data)
          setStep(step + 1)
        },
      })
    } else {
      setStep(step + 1)
    }
  }

  const handleClose = () => {
    setStep(0)
    setAnswers({ role: '', critical_messages: '', can_wait: '', priority_senders: '' })
    setResult(null)
    onOpenChange(false)
  }

  const canProceed = !isReviewStep && currentStep && answers[currentStep.field].trim().length > 0

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            AI Priority Definition Wizard
          </DialogTitle>
          <DialogDescription>
            Answer a few questions and we'll generate personalized priority definitions.
          </DialogDescription>
        </DialogHeader>

        {isReviewStep && result ? (
          <div className="space-y-4">
            <p className="text-sm font-medium">Generated Definitions</p>
            <div className="space-y-3 text-sm">
              <div>
                <Label className="text-xs font-medium text-muted-foreground">P0 — Urgent</Label>
                <p className="mt-0.5 bg-muted/50 rounded-md p-2">{result.p0_definition}</p>
              </div>
              <div>
                <Label className="text-xs font-medium text-muted-foreground">P1 — Important</Label>
                <p className="mt-0.5 bg-muted/50 rounded-md p-2">{result.p1_definition}</p>
              </div>
              <div>
                <Label className="text-xs font-medium text-muted-foreground">P2 — Notable</Label>
                <p className="mt-0.5 bg-muted/50 rounded-md p-2">{result.p2_definition}</p>
              </div>
              <div>
                <Label className="text-xs font-medium text-muted-foreground">P3 — Low</Label>
                <p className="mt-0.5 bg-muted/50 rounded-md p-2">{result.p3_definition}</p>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={handleClose}>
                Cancel
              </Button>
              <Button size="sm" onClick={() => onApply(result)}>
                Apply Definitions
              </Button>
            </div>
          </div>
        ) : currentStep ? (
          <div className="space-y-4">
            {/* Step indicator */}
            <div className="flex gap-1">
              {STEPS.map((_, i) => (
                <div
                  key={i}
                  className={`h-1 flex-1 rounded-full ${
                    i <= step ? 'bg-primary' : 'bg-muted'
                  }`}
                />
              ))}
            </div>

            <div className="space-y-2">
              <Label className="text-sm font-medium">{currentStep.question}</Label>
              <Textarea
                rows={3}
                placeholder={currentStep.placeholder}
                value={answers[currentStep.field]}
                onChange={(e) =>
                  setAnswers({ ...answers, [currentStep.field]: e.target.value })
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
                disabled={!canProceed && !isLastStep || generateDefs.isPending}
                onClick={handleNext}
              >
                {generateDefs.isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                    Generating...
                  </>
                ) : isLastStep ? (
                  'Generate'
                ) : (
                  'Next'
                )}
              </Button>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
