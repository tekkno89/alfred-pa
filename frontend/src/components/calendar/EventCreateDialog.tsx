import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useCalendars, useCreateCalendarEvent } from '@/hooks/useCalendar'
import type { CalendarEvent } from '@/types'

interface EventCreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialDate?: Date
  editEvent?: CalendarEvent | null
}

function toLocalDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function EventCreateDialog({ open, onOpenChange, initialDate, editEvent }: EventCreateDialogProps) {
  const { data: calData } = useCalendars()
  const createEvent = useCreateCalendarEvent()
  const calendars = calData?.calendars?.filter((c) => c.visible && c.access_role !== 'reader') ?? []

  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [location, setLocation] = useState('')
  const [allDay, setAllDay] = useState(false)
  const [startDate, setStartDate] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endDate, setEndDate] = useState('')
  const [endTime, setEndTime] = useState('')
  const [calendarKey, setCalendarKey] = useState('')
  const [attendeesInput, setAttendeesInput] = useState('')

  useEffect(() => {
    if (!open) return

    if (editEvent) {
      setTitle(editEvent.title)
      setDescription(editEvent.description || '')
      setLocation(editEvent.location || '')
      setAllDay(editEvent.all_day)
      setCalendarKey(`${editEvent.account_label}:${editEvent.calendar_id}`)
      setAttendeesInput(editEvent.attendees.map((a) => a.email).join(', '))

      if (editEvent.all_day) {
        setStartDate(editEvent.start)
        setEndDate(editEvent.end || editEvent.start)
        setStartTime('')
        setEndTime('')
      } else {
        const startDt = new Date(editEvent.start)
        setStartDate(toLocalDate(startDt))
        setStartTime(startDt.toTimeString().slice(0, 5))
        if (editEvent.end) {
          const endDt = new Date(editEvent.end)
          setEndDate(toLocalDate(endDt))
          setEndTime(endDt.toTimeString().slice(0, 5))
        }
      }
    } else {
      const base = initialDate || new Date()
      setTitle('')
      setDescription('')
      setLocation('')
      setAllDay(false)
      setStartDate(toLocalDate(base))

      if (initialDate && (initialDate.getHours() !== 0 || initialDate.getMinutes() !== 0)) {
        // Use exact time from time slot click
        const h = initialDate.getHours()
        const m = initialDate.getMinutes()
        setStartTime(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`)
        // End time = start + 1 hour
        const endH = (h + 1) % 24
        setEndTime(`${String(endH).padStart(2, '0')}:${String(m).padStart(2, '0')}`)
      } else {
        // Round to next hour (from "New Event" button or date-only click)
        const roundedHour = base.getHours() + 1
        setStartTime(`${String(roundedHour % 24).padStart(2, '0')}:00`)
        setEndTime(`${String((roundedHour + 1) % 24).padStart(2, '0')}:00`)
      }
      setEndDate(toLocalDate(base))
      setAttendeesInput('')

      if (calendars.length > 0 && !calendarKey) {
        const primary = calendars.find((c) => c.primary)
        const cal = primary || calendars[0]
        setCalendarKey(`${cal.account_label}:${cal.id}`)
      }
    }
  }, [open, initialDate, editEvent])

  // Set default calendar when calendars load
  useEffect(() => {
    if (!calendarKey && calendars.length > 0) {
      const primary = calendars.find((c) => c.primary)
      const cal = primary || calendars[0]
      setCalendarKey(`${cal.account_label}:${cal.id}`)
    }
  }, [calendars, calendarKey])

  const handleSubmit = () => {
    if (!title.trim()) return

    const [accountLabel, calendarId] = calendarKey.split(':')
    const attendees = attendeesInput
      .split(',')
      .map((e) => e.trim())
      .filter((e) => e.includes('@'))

    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
    const tzOffset = new Date().toLocaleString('en-US', { timeZone: tz, timeZoneName: 'longOffset' })
    const offsetMatch = tzOffset.match(/GMT([+-]\d{2}:\d{2})/)
    const offset = offsetMatch ? offsetMatch[1] : '+00:00'

    let start: string
    let end: string | undefined

    if (allDay) {
      start = startDate
      end = endDate || startDate
    } else {
      start = `${startDate}T${startTime}:00${offset}`
      if (endTime) {
        end = `${endDate || startDate}T${endTime}:00${offset}`
      }
    }

    createEvent.mutate(
      {
        title: title.trim(),
        description: description.trim() || undefined,
        location: location.trim() || undefined,
        start,
        end,
        all_day: allDay,
        calendar_id: calendarId || 'primary',
        account_label: accountLabel || 'default',
        attendees: attendees.length > 0 ? attendees : undefined,
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
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{editEvent ? 'Edit Event' : 'New Event'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Title */}
          <div>
            <Label htmlFor="event-title">Title</Label>
            <Input
              id="event-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Event title"
              autoFocus
            />
          </div>

          {/* All day toggle */}
          <div className="flex items-center gap-2">
            <Switch checked={allDay} onCheckedChange={setAllDay} id="all-day" />
            <Label htmlFor="all-day" className="text-sm cursor-pointer">All day</Label>
          </div>

          {/* Date/Time */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Start {allDay ? 'date' : ''}</Label>
              <Input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            {!allDay && (
              <div>
                <Label>Start time</Label>
                <Input
                  type="time"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                />
              </div>
            )}
            <div>
              <Label>End {allDay ? 'date' : ''}</Label>
              <Input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
            {!allDay && (
              <div>
                <Label>End time</Label>
                <Input
                  type="time"
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                />
              </div>
            )}
          </div>

          {/* Calendar selector */}
          {calendars.length > 0 && (
            <div>
              <Label>Calendar</Label>
              <Select value={calendarKey} onValueChange={setCalendarKey}>
                <SelectTrigger>
                  <SelectValue placeholder="Select calendar" />
                </SelectTrigger>
                <SelectContent>
                  {calendars.map((cal) => (
                    <SelectItem
                      key={`${cal.account_label}:${cal.id}`}
                      value={`${cal.account_label}:${cal.id}`}
                    >
                      <div className="flex items-center gap-2">
                        <div
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: cal.color }}
                        />
                        {cal.name}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Location */}
          <div>
            <Label htmlFor="event-location">Location</Label>
            <Input
              id="event-location"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Add location"
            />
          </div>

          {/* Description */}
          <div>
            <Label htmlFor="event-desc">Description</Label>
            <Textarea
              id="event-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Add description"
              rows={2}
            />
          </div>

          {/* Attendees */}
          <div>
            <Label htmlFor="event-attendees">Attendees</Label>
            <Input
              id="event-attendees"
              value={attendeesInput}
              onChange={(e) => setAttendeesInput(e.target.value)}
              placeholder="email1@example.com, email2@example.com"
            />
            <p className="text-xs text-muted-foreground mt-1">Comma-separated email addresses</p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!title.trim() || createEvent.isPending}>
            {createEvent.isPending ? 'Creating...' : editEvent ? 'Save' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
