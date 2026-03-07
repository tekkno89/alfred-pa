import { useMemo } from 'react'
import type { CalendarEvent } from '@/types'

interface MonthlyViewProps {
  currentDate: Date
  events: CalendarEvent[]
  onEventClick: (event: CalendarEvent) => void
  onDayClick: (date: Date) => void
}

function getDaysInMonth(date: Date): Date[] {
  const year = date.getFullYear()
  const month = date.getMonth()
  const firstDay = new Date(year, month, 1)
  const lastDay = new Date(year, month + 1, 0)

  // Start from the Sunday before the first day
  const start = new Date(firstDay)
  start.setDate(start.getDate() - start.getDay())

  // End on the Saturday after the last day
  const end = new Date(lastDay)
  if (end.getDay() !== 6) {
    end.setDate(end.getDate() + (6 - end.getDay()))
  }

  const days: Date[] = []
  const current = new Date(start)
  while (current <= end) {
    days.push(new Date(current))
    current.setDate(current.getDate() + 1)
  }
  return days
}

function getEventDate(event: CalendarEvent): string {
  try {
    const d = new Date(event.start)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  } catch {
    return ''
  }
}

function formatTime(event: CalendarEvent): string {
  if (event.all_day) return ''
  try {
    return new Date(event.start).toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

export function MonthlyView({ currentDate, events, onEventClick, onDayClick }: MonthlyViewProps) {
  const days = useMemo(() => getDaysInMonth(currentDate), [currentDate])
  const today = new Date()
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  const currentMonth = currentDate.getMonth()

  const eventsByDate = useMemo(() => {
    const map: Record<string, CalendarEvent[]> = {}
    for (const event of events) {
      const key = getEventDate(event)
      if (!map[key]) map[key] = []
      map[key].push(event)
    }
    return map
  }, [events])

  const weekDays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

  return (
    <div className="flex flex-col flex-1">
      {/* Header row */}
      <div className="grid grid-cols-7 border-b">
        {weekDays.map((day) => (
          <div key={day} className="p-2 text-xs font-medium text-muted-foreground text-center">
            {day}
          </div>
        ))}
      </div>

      {/* Day cells */}
      <div className="grid grid-cols-7 flex-1 auto-rows-fr">
        {days.map((day) => {
          const dateStr = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
          const isToday = dateStr === todayStr
          const isOutside = day.getMonth() !== currentMonth
          const dayEvents = eventsByDate[dateStr] || []
          const maxShow = 3

          return (
            <div
              key={dateStr}
              className="border-b border-r p-1 min-h-[80px] cursor-pointer hover:bg-muted/30 transition-colors"
              onClick={() => onDayClick(day)}
            >
              <div className="flex justify-between items-start">
                <span
                  className={`text-xs inline-flex items-center justify-center h-6 w-6 rounded-full ${
                    isToday
                      ? 'bg-primary text-primary-foreground font-bold'
                      : isOutside
                        ? 'text-muted-foreground/50'
                        : 'text-foreground'
                  }`}
                >
                  {day.getDate()}
                </span>
              </div>

              <div className="mt-0.5 space-y-0.5">
                {dayEvents.slice(0, maxShow).map((event) => (
                  <div
                    key={event.id}
                    className="flex items-center gap-1 text-xs rounded px-1 py-0.5 hover:bg-muted/60 cursor-pointer truncate"
                    onClick={(e) => {
                      e.stopPropagation()
                      onEventClick(event)
                    }}
                  >
                    <div
                      className="h-1.5 w-1.5 rounded-full shrink-0"
                      style={{ backgroundColor: event.color }}
                    />
                    {!event.all_day && (
                      <span className="text-muted-foreground shrink-0">{formatTime(event)}</span>
                    )}
                    <span className="truncate">{event.title}</span>
                  </div>
                ))}
                {dayEvents.length > maxShow && (
                  <div
                    className="text-xs text-muted-foreground pl-1 cursor-pointer hover:text-foreground"
                    onClick={(e) => {
                      e.stopPropagation()
                      onDayClick(day)
                    }}
                  >
                    +{dayEvents.length - maxShow} more
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
