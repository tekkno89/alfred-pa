import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { WebhookEventType } from '@/types'

const EVENT_TYPES: { value: WebhookEventType; label: string }[] = [
  { value: 'focus_started', label: 'Focus Started' },
  { value: 'focus_ended', label: 'Focus Ended' },
  { value: 'focus_bypass', label: 'Focus Bypass' },
  { value: 'pomodoro_work_started', label: 'Pomodoro Work Started' },
  { value: 'pomodoro_break_started', label: 'Pomodoro Break Started' },
]

interface WebhookFormProps {
  onSubmit: (data: {
    name: string
    url: string
    event_types: WebhookEventType[]
  }) => void
  isLoading?: boolean
}

export function WebhookForm({ onSubmit, isLoading }: WebhookFormProps) {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [selectedEvents, setSelectedEvents] = useState<WebhookEventType[]>([])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !url.trim() || selectedEvents.length === 0) return

    onSubmit({
      name: name.trim(),
      url: url.trim(),
      event_types: selectedEvents,
    })

    // Reset form
    setName('')
    setUrl('')
    setSelectedEvents([])
  }

  const toggleEvent = (event: WebhookEventType) => {
    setSelectedEvents((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event]
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            placeholder="My Webhook"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="url">URL</Label>
          <Input
            id="url"
            type="url"
            placeholder="https://example.com/webhook"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label>Event Types</Label>
        <div className="flex flex-wrap gap-2">
          {EVENT_TYPES.map((event) => (
            <button
              key={event.value}
              type="button"
              onClick={() => toggleEvent(event.value)}
              className={`px-3 py-1 rounded-full text-sm ${
                selectedEvents.includes(event.value)
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/80'
              }`}
            >
              {event.label}
            </button>
          ))}
        </div>
      </div>

      <Button
        type="submit"
        disabled={isLoading || !name.trim() || !url.trim() || selectedEvents.length === 0}
      >
        <Plus className="h-4 w-4 mr-2" />
        {isLoading ? 'Adding...' : 'Add Webhook'}
      </Button>
    </form>
  )
}
