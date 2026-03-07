import { useNavigate } from 'react-router-dom'
import { CalendarDays, Plus } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { useTodayEvents } from '@/hooks/useCalendar'
import type { CalendarEvent } from '@/types'

function formatEventTime(event: CalendarEvent): string {
  if (event.all_day) return 'All day'
  try {
    const start = new Date(event.start)
    return start.toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

export function CalendarCard() {
  const navigate = useNavigate()
  const { data, isLoading } = useTodayEvents()
  const events = data?.events ?? []

  return (
    <Card
      className="cursor-pointer hover:shadow-md transition-shadow relative h-full flex flex-col"
      onClick={() => navigate('/calendar')}
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <CalendarDays className="h-4 w-4" />
          Calendar
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : events.length === 0 ? (
          <p className="text-sm text-muted-foreground">No events today</p>
        ) : (
          <div className="space-y-1.5">
            {events.slice(0, 8).map((event) => (
              <div
                key={event.id}
                className="flex items-center gap-1.5 text-sm cursor-pointer hover:bg-muted/50 rounded px-1 -mx-1"
                onClick={(e) => {
                  e.stopPropagation()
                  navigate(`/calendar?event=${event.id}&calendar=${event.calendar_id}&account=${event.account_label}`)
                }}
              >
                <div
                  className="h-2 w-2 rounded-full shrink-0"
                  style={{ backgroundColor: event.color }}
                />
                <span className="text-xs text-muted-foreground shrink-0 w-16">
                  {formatEventTime(event)}
                </span>
                <span className="truncate flex-1">{event.title}</span>
              </div>
            ))}
            {events.length > 8 && (
              <p className="text-xs text-muted-foreground pl-1">
                +{events.length - 8} more
              </p>
            )}
          </div>
        )}
      </CardContent>
      <button
        className="absolute bottom-3 right-3 h-8 w-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-sm hover:bg-primary/90 transition-colors"
        onClick={(e) => {
          e.stopPropagation()
          navigate('/calendar?create=true')
        }}
      >
        <Plus className="h-6 w-6 stroke-[2.5]" />
      </button>
    </Card>
  )
}
