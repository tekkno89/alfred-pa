import { useState } from 'react'
import { AlertTriangle, AlertCircle, Bookmark, VolumeX, Eye } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Textarea } from '@/components/ui/textarea'
import { useSubmitFeedback } from '@/hooks/useTriage'
import type { TriageClassification } from '@/types'

const PRIORITY_OPTIONS = [
  { value: 'p0', label: 'P0 — Urgent', description: 'Immediate attention required', icon: AlertTriangle },
  { value: 'p1', label: 'P1 — Important', description: 'Time-sensitive but can wait', icon: AlertCircle },
  { value: 'p2', label: 'P2 — Notable', description: 'Noteworthy but can wait', icon: Bookmark },
  { value: 'p3', label: 'P3 — Low', description: 'Low priority', icon: VolumeX },
  { value: 'review', label: 'Review', description: 'Needs manual review', icon: Eye },
]

interface CorrectClassificationDialogProps {
  classification: TriageClassification | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CorrectClassificationDialog({
  classification,
  open,
  onOpenChange,
}: CorrectClassificationDialogProps) {
  const [priority, setPriority] = useState<string>(classification?.priority_level || 'p2')
  const [feedbackText, setFeedbackText] = useState('')
  const submitFeedback = useSubmitFeedback()

  const handleSubmit = () => {
    if (!classification) return

    submitFeedback.mutate(
      {
        classification_id: classification.id,
        was_correct: false,
        correct_priority: priority as 'p0' | 'p1' | 'p2' | 'p3' | 'review',
        feedback_text: feedbackText || null,
      },
      {
        onSuccess: () => {
          onOpenChange(false)
          setFeedbackText('')
        },
      }
    )
  }

  const currentPriority = classification?.priority_level

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Correct Classification</DialogTitle>
          <DialogDescription>
            Help improve the AI by correcting this classification.
            The classification will be updated and your feedback will be used
            to improve future classifications.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>Current classification: {currentPriority?.toUpperCase()}</Label>
            <p className="text-sm text-muted-foreground">
              {classification?.abstract || 'Message'}
            </p>
          </div>

          <div className="space-y-2">
            <Label>Correct priority</Label>
            <RadioGroup value={priority} onValueChange={setPriority}>
              {PRIORITY_OPTIONS.map((option) => {
                const Icon = option.icon
                return (
                  <div
                    key={option.value}
                    className="flex items-center space-x-3 space-y-0 rounded-md border p-3"
                  >
                    <RadioGroupItem value={option.value} id={option.value} />
                    <Label
                      htmlFor={option.value}
                      className="flex items-center gap-2 cursor-pointer flex-1"
                    >
                      <Icon className="h-4 w-4" />
                      <div>
                        <span className="font-medium">{option.label}</span>
                        <p className="text-xs text-muted-foreground">
                          {option.description}
                        </p>
                      </div>
                    </Label>
                  </div>
                )
              })}
            </RadioGroup>
          </div>

          <div className="space-y-2">
            <Label htmlFor="feedback">Why was this misclassified? (optional)</Label>
            <Textarea
              id="feedback"
              placeholder="e.g., This was actually urgent because..."
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value)}
              rows={3}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitFeedback.isPending}>
            {submitFeedback.isPending ? 'Saving...' : 'Save Correction'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
