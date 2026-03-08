import { useMemo } from 'react'
import type { CalendarEvent } from '@/types'
import { dateKey } from './calendarLayout'
import type { LayoutItem } from './calendarLayout'
import { TimeGrid } from './TimeGrid'

interface WeeklyViewProps {
  currentDate: Date
  events: CalendarEvent[]
  onEventClick: (event: CalendarEvent) => void
  onTimeSlotClick?: (date: Date) => void
}

function getWeekDays(date: Date): Date[] {
  const start = new Date(date)
  start.setDate(start.getDate() - start.getDay())
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start)
    d.setDate(d.getDate() + i)
    return d
  })
}

export function WeeklyView({ currentDate, events, onEventClick, onTimeSlotClick }: WeeklyViewProps) {
  const days = useMemo(() => getWeekDays(currentDate), [currentDate])
  const dayKeys = useMemo(() => days.map(d => dateKey(d)), [days])

  // All-day strip layout: spanning bars with row packing
  const allDayLayout = useMemo(() => {
    const items: LayoutItem[] = []
    const seen = new Set<string>()

    for (const event of events) {
      if (seen.has(event.id)) continue

      const startStr = event.all_day
        ? event.start.slice(0, 10)
        : dateKey(new Date(event.start))
      const endStr = event.end
        ? (event.all_day ? event.end.slice(0, 10) : dateKey(new Date(event.end)))
        : ''
      const isMultiDay = !!endStr && endStr > startStr

      if (!event.all_day && !isMultiDay) continue
      seen.add(event.id)

      // Calculate start column (clamp to visible week)
      let startCol: number
      if (startStr < dayKeys[0]) {
        startCol = 0
      } else {
        startCol = dayKeys.indexOf(startStr)
        if (startCol === -1) continue // starts after this week
      }

      // Calculate end column (exclusive for CSS grid)
      let endCol: number
      if (!isMultiDay) {
        endCol = startCol + 1
      } else if (event.all_day) {
        // All-day end date is exclusive (Google convention)
        if (endStr > dayKeys[6]) {
          endCol = 7
        } else {
          const idx = dayKeys.indexOf(endStr)
          endCol = idx === -1 ? 7 : idx
        }
      } else {
        // Timed multi-day: include the end date
        if (endStr > dayKeys[6]) {
          endCol = 7
        } else {
          const idx = dayKeys.indexOf(endStr)
          endCol = idx === -1 ? 7 : idx + 1
        }
      }

      if (endCol <= startCol) endCol = startCol + 1

      items.push({ event, startCol, endCol })
    }

    // Sort: earlier start first, then longer spans first
    items.sort((a, b) => a.startCol - b.startCol || (b.endCol - b.startCol) - (a.endCol - a.startCol))

    // Greedy row packing
    const rows: LayoutItem[][] = []
    for (const item of items) {
      let placed = false
      for (const row of rows) {
        if (!row.some(r => r.startCol < item.endCol && item.startCol < r.endCol)) {
          row.push(item)
          placed = true
          break
        }
      }
      if (!placed) rows.push([item])
    }

    return rows
  }, [events, dayKeys])

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
