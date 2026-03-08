import { useMemo } from 'react'
import type { CalendarEvent } from '@/types'
import { dateKey } from './calendarLayout'
import type { LayoutItem } from './calendarLayout'
import { TimeGrid } from './TimeGrid'

interface DailyViewProps {
  currentDate: Date
  events: CalendarEvent[]
  onEventClick: (event: CalendarEvent) => void
  onTimeSlotClick?: (date: Date) => void
}

export function DailyView({ currentDate, events, onEventClick, onTimeSlotClick }: DailyViewProps) {
  const days = useMemo(() => [new Date(currentDate)], [currentDate])
  const dayStr = dateKey(currentDate)

  // All-day layout for a single day: every all-day/multi-day event gets col 0..1
  const allDayLayout = useMemo(() => {
    const items: LayoutItem[] = []

    for (const event of events) {
      const startStr = event.all_day
        ? event.start.slice(0, 10)
        : dateKey(new Date(event.start))
      const endStr = event.end
        ? (event.all_day ? event.end.slice(0, 10) : dateKey(new Date(event.end)))
        : ''
      const isMultiDay = !!endStr && endStr > startStr

      if (!event.all_day && !isMultiDay) continue

      // Check if this event overlaps the current day
      if (event.all_day) {
        // All-day: start <= dayStr and end (exclusive) > dayStr
        if (startStr > dayStr) continue
        if (endStr && endStr <= dayStr) continue
      } else {
        // Multi-day timed: start date <= dayStr and end date >= dayStr
        if (startStr > dayStr) continue
        if (endStr < dayStr) continue
      }

      items.push({ event, startCol: 0, endCol: 1 })
    }

    if (items.length === 0) return []

    // Each item gets its own row (no spanning logic needed for single day)
    return items.map((item) => [item])
  }, [events, dayStr])

  return (
    <TimeGrid
      days={days}
      events={events}
      allDayLayout={allDayLayout}
      onEventClick={onEventClick}
      onTimeSlotClick={onTimeSlotClick}
    />
  )
}
