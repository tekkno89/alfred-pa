import { useState } from 'react'
import { MapPin, Clock, Users, ExternalLink, Trash2, Pencil, CalendarDays } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useDeleteCalendarEvent } from '@/hooks/useCalendar'
import type { CalendarEvent } from '@/types'

interface EventDetailDialogProps {
  event: CalendarEvent | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onEdit: (event: CalendarEvent) => void
}

function formatDateTime(dateStr: string, allDay: boolean): string {
  if (allDay) {
    return new Date(dateStr + 'T00:00:00').toLocaleDateString(undefined, {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    })
  }
  return new Date(dateStr).toLocaleString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function formatTimeRange(event: CalendarEvent): string {
  if (event.all_day) return 'All day'
  const start = formatDateTime(event.start, false)
  if (!event.end) return start
  const endTime = new Date(event.end).toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  })
  return `${start} – ${endTime}`
}

export function EventDetailDialog({ event, open, onOpenChange, onEdit }: EventDetailDialogProps) {
  const deleteEvent = useDeleteCalendarEvent()
  const [deleteOpen, setDeleteOpen] = useState(false)

  if (!event) return null

  const isRecurring = !!event.recurring_event_id || !!event.recurrence

  const handleDelete = (scope: 'this' | 'all' = 'this') => {
    deleteEvent.mutate(
      {
        eventId: scope === 'all' && event.recurring_event_id ? event.recurring_event_id : event.id,
        calendarId: event.calendar_id,
        accountLabel: event.account_label,
      },
      {
        onSuccess: () => {
          setDeleteOpen(false)
          onOpenChange(false)
        },
      }
    )
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <div className="flex items-start gap-3">
              <div
                className="h-3 w-3 rounded-full mt-1.5 shrink-0"
                style={{ backgroundColor: event.color }}
              />
              <DialogTitle className="text-lg leading-tight">{event.title}</DialogTitle>
            </div>
          </DialogHeader>

          <div className="space-y-3">
            {/* Time */}
            <div className="flex items-start gap-2 text-sm">
              <Clock className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
              <span>{formatTimeRange(event)}</span>
            </div>

            {/* Location */}
            {event.location && (
              <div className="flex items-start gap-2 text-sm">
                <MapPin className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                <span>{event.location}</span>
              </div>
            )}

            {/* Calendar */}
            <div className="flex items-start gap-2 text-sm">
              <CalendarDays className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
              <span className="text-muted-foreground">{event.calendar_id}</span>
            </div>

            {/* Description */}
            {event.description && (
              <p className="text-sm text-muted-foreground whitespace-pre-wrap border-t pt-3">
                {event.description}
              </p>
            )}

            {/* Attendees */}
            {event.attendees.length > 0 && (
              <div className="border-t pt-3">
                <div className="flex items-center gap-2 text-sm font-medium mb-1">
                  <Users className="h-4 w-4 text-muted-foreground" />
                  Attendees ({event.attendees.length})
                </div>
                <div className="space-y-1 ml-6">
                  {event.attendees.map((a) => (
                    <div key={a.email} className="text-sm text-muted-foreground">
                      {a.email}
                      {a.response_status !== 'needsAction' && (
                        <span className="ml-1 text-xs">
                          ({a.response_status})
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between pt-2 border-t">
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  onOpenChange(false)
                  onEdit(event)
                }}
              >
                <Pencil className="h-3.5 w-3.5 mr-1" />
                Edit
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={() => setDeleteOpen(true)}
                disabled={deleteEvent.isPending}
              >
                <Trash2 className="h-3.5 w-3.5 mr-1" />
                Delete
              </Button>
            </div>
            {event.html_link && (
              <a
                href={event.html_link}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Open
              </a>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete event</AlertDialogTitle>
            <AlertDialogDescription>
              {isRecurring
                ? 'This is a recurring event. Would you like to delete just this instance or all instances?'
                : `Are you sure you want to delete "${event.title}"?`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            {isRecurring ? (
              <>
                <AlertDialogAction onClick={() => handleDelete('this')}>
                  This event
                </AlertDialogAction>
                <AlertDialogAction
                  onClick={() => handleDelete('all')}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  All events
                </AlertDialogAction>
              </>
            ) : (
              <AlertDialogAction
                onClick={() => handleDelete('this')}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                Delete
              </AlertDialogAction>
            )}
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
