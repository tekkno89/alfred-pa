import { useMemo, useRef, useEffect } from 'react'
import type { CalendarEvent } from '@/types'

interface WeeklyViewProps {
  currentDate: Date
  events: CalendarEvent[]
  onEventClick: (event: CalendarEvent) => void
}

const HOUR_HEIGHT = 60 // px per hour
const HOURS = Array.from({ length: 24 }, (_, i) => i)

function getWeekDays(date: Date): Date[] {
  const start = new Date(date)
  start.setDate(start.getDate() - start.getDay())
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start)
    d.setDate(d.getDate() + i)
    return d
  })
}

function dateKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function getEventPosition(event: CalendarEvent): { top: number; height: number } | null {
  if (event.all_day) return null
  try {
    const start = new Date(event.start)
    const end = event.end ? new Date(event.end) : new Date(start.getTime() + 60 * 60 * 1000)
    const startMinutes = start.getHours() * 60 + start.getMinutes()
    const endMinutes = end.getHours() * 60 + end.getMinutes()
    const duration = Math.max(endMinutes - startMinutes, 15)
    return {
      top: (startMinutes / 60) * HOUR_HEIGHT,
      height: (duration / 60) * HOUR_HEIGHT,
    }
  } catch {
    return null
  }
}

function formatHour(hour: number): string {
  if (hour === 0) return '12 AM'
  if (hour < 12) return `${hour} AM`
  if (hour === 12) return '12 PM'
  return `${hour - 12} PM`
}

function formatEventTime(event: CalendarEvent): string {
  try {
    return new Date(event.start).toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

export function WeeklyView({ currentDate, events, onEventClick }: WeeklyViewProps) {
  const days = useMemo(() => getWeekDays(currentDate), [currentDate])
  const scrollRef = useRef<HTMLDivElement>(null)
  const today = new Date()
  const todayKey = dateKey(today)

  // Scroll to current hour on mount
  useEffect(() => {
    if (scrollRef.current) {
      const hour = Math.max(today.getHours() - 1, 0)
      scrollRef.current.scrollTop = hour * HOUR_HEIGHT
    }
  }, [])

  // Group events by date
  const eventsByDate = useMemo(() => {
    const map: Record<string, CalendarEvent[]> = {}
    const allDay: Record<string, CalendarEvent[]> = {}
    for (const event of events) {
      try {
        const d = new Date(event.start)
        const key = dateKey(d)
        if (event.all_day) {
          if (!allDay[key]) allDay[key] = []
          allDay[key].push(event)
        } else {
          if (!map[key]) map[key] = []
          map[key].push(event)
        }
      } catch {
        // skip malformed events
      }
    }
    return { timed: map, allDay }
  }, [events])

  // Current time indicator position
  const nowMinutes = today.getHours() * 60 + today.getMinutes()
  const nowTop = (nowMinutes / 60) * HOUR_HEIGHT

  const hasAllDay = days.some((d) => (eventsByDate.allDay[dateKey(d)] || []).length > 0)

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Day headers */}
      <div className="flex border-b shrink-0">
        <div className="w-16 shrink-0" />
        {days.map((day) => {
          const key = dateKey(day)
          const isToday = key === todayKey
          return (
            <div key={key} className="flex-1 text-center py-2 border-l">
              <div className="text-xs text-muted-foreground">
                {day.toLocaleDateString(undefined, { weekday: 'short' })}
              </div>
              <div
                className={`text-sm font-medium inline-flex items-center justify-center h-7 w-7 rounded-full ${
                  isToday ? 'bg-primary text-primary-foreground' : ''
                }`}
              >
                {day.getDate()}
              </div>
            </div>
          )
        })}
      </div>

      {/* All-day row */}
      {hasAllDay && (
        <div className="flex border-b shrink-0">
          <div className="w-16 shrink-0 text-xs text-muted-foreground p-1 text-right pr-2">
            all-day
          </div>
          {days.map((day) => {
            const key = dateKey(day)
            const dayAllDay = eventsByDate.allDay[key] || []
            return (
              <div key={key} className="flex-1 border-l p-0.5 space-y-0.5 min-h-[28px]">
                {dayAllDay.map((event) => (
                  <div
                    key={event.id}
                    className="text-xs rounded px-1 py-0.5 truncate cursor-pointer text-white"
                    style={{ backgroundColor: event.color }}
                    onClick={() => onEventClick(event)}
                  >
                    {event.title}
                  </div>
                ))}
              </div>
            )
          })}
        </div>
      )}

      {/* Time grid */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="flex relative" style={{ height: 24 * HOUR_HEIGHT }}>
          {/* Time labels */}
          <div className="w-16 shrink-0 relative">
            {HOURS.map((hour) => (
              <div
                key={hour}
                className="absolute w-full text-right pr-2 text-xs text-muted-foreground"
                style={{ top: hour * HOUR_HEIGHT - 8 }}
              >
                {hour > 0 ? formatHour(hour) : ''}
              </div>
            ))}
          </div>

          {/* Day columns */}
          {days.map((day) => {
            const key = dateKey(day)
            const isToday = key === todayKey
            const dayEvents = eventsByDate.timed[key] || []

            return (
              <div key={key} className="flex-1 relative border-l">
                {/* Hour lines */}
                {HOURS.map((hour) => (
                  <div
                    key={hour}
                    className="absolute w-full border-t border-border/50"
                    style={{ top: hour * HOUR_HEIGHT }}
                  />
                ))}

                {/* Current time indicator */}
                {isToday && (
                  <div
                    className="absolute w-full z-10 pointer-events-none"
                    style={{ top: nowTop }}
                  >
                    <div className="flex items-center">
                      <div className="h-2.5 w-2.5 rounded-full bg-red-500 -ml-1" />
                      <div className="flex-1 h-0.5 bg-red-500" />
                    </div>
                  </div>
                )}

                {/* Events */}
                {dayEvents.map((event) => {
                  const pos = getEventPosition(event)
                  if (!pos) return null
                  return (
                    <div
                      key={event.id}
                      className="absolute left-0.5 right-0.5 rounded px-1 py-0.5 text-xs cursor-pointer overflow-hidden text-white z-[5]"
                      style={{
                        top: pos.top,
                        height: Math.max(pos.height, 18),
                        backgroundColor: event.color,
                        opacity: 0.9,
                      }}
                      onClick={() => onEventClick(event)}
                    >
                      <div className="font-medium truncate">{event.title}</div>
                      {pos.height > 30 && (
                        <div className="text-white/80 truncate">{formatEventTime(event)}</div>
                      )}
                    </div>
                  )
                })}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
