import { useRef, useEffect, useMemo } from 'react'
import type { CalendarEvent } from '@/types'
import {
  HOUR_HEIGHT,
  HOURS,
  EVENT_WIDTH_PCT,
  dateKey,
  getEventPosition,
  formatHour,
  formatEventTime,
  computeOverlapColumns,
} from './calendarLayout'
import type { LayoutItem } from './calendarLayout'

interface TimeGridProps {
  days: Date[]
  events: CalendarEvent[]
  allDayLayout: LayoutItem[][]
  onEventClick: (event: CalendarEvent) => void
  onTimeSlotClick?: (date: Date) => void
}

export function TimeGrid({ days, events, allDayLayout, onEventClick, onTimeSlotClick }: TimeGridProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const today = new Date()
  const todayKey = dateKey(today)
  const colCount = days.length

  const dayKeys = useMemo(() => days.map(d => dateKey(d)), [days])

  // Scroll to current hour on mount
  useEffect(() => {
    if (scrollRef.current) {
      const hour = Math.max(today.getHours() - 1, 0)
      scrollRef.current.scrollTop = hour * HOUR_HEIGHT
    }
  }, [])

  // Single-day timed events for the time grid
  const timedByDate = useMemo(() => {
    const map: Record<string, CalendarEvent[]> = {}
    for (const event of events) {
      try {
        if (event.all_day) continue
        const startStr = dateKey(new Date(event.start))
        const endStr = event.end ? dateKey(new Date(event.end)) : ''
        // Multi-day timed events go in the all-day strip instead
        if (endStr && endStr > startStr) continue
        if (!map[startStr]) map[startStr] = []
        map[startStr].push(event)
      } catch {
        // skip malformed
      }
    }
    return map
  }, [events])

  // Compute overlap columns per day
  const overlapByDate = useMemo(() => {
    const map: Record<string, ReturnType<typeof computeOverlapColumns>> = {}
    for (const key of dayKeys) {
      const dayEvents = timedByDate[key]
      if (dayEvents && dayEvents.length > 0) {
        map[key] = computeOverlapColumns(dayEvents)
      }
    }
    return map
  }, [timedByDate, dayKeys])

  // Current time indicator position
  const nowMinutes = today.getHours() * 60 + today.getMinutes()
  const nowTop = (nowMinutes / 60) * HOUR_HEIGHT

  const handleColumnClick = (day: Date, e: React.MouseEvent<HTMLDivElement>) => {
    if (!onTimeSlotClick) return
    const rect = e.currentTarget.getBoundingClientRect()
    const yOffset = e.clientY - rect.top
    const totalMinutes = (yOffset / HOUR_HEIGHT) * 60
    // Round to nearest 15 minutes
    const rounded = Math.round(totalMinutes / 15) * 15
    const hours = Math.floor(rounded / 60)
    const minutes = rounded % 60

    const clickedDate = new Date(day)
    clickedDate.setHours(hours, minutes, 0, 0)
    onTimeSlotClick(clickedDate)
  }

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

      {/* All-day strip */}
      {allDayLayout.length > 0 && (
        <div className="flex border-b shrink-0">
          <div className="w-16 shrink-0 text-xs text-muted-foreground p-1 text-right pr-2 flex items-start justify-end pt-1.5">
            all-day
          </div>
          <div className="flex-1 relative">
            {/* Column borders */}
            <div className={`absolute inset-0 grid pointer-events-none`} style={{ gridTemplateColumns: `repeat(${colCount}, 1fr)` }}>
              {days.map((day) => (
                <div key={dateKey(day)} className="border-l" />
              ))}
            </div>
            {/* Event bars */}
            <div
              className="relative gap-y-0.5 py-0.5"
              style={{ display: 'grid', gridTemplateColumns: `repeat(${colCount}, 1fr)`, gridAutoRows: '24px' }}
            >
              {allDayLayout.map((row, rowIdx) =>
                row.map(({ event, startCol, endCol }) => (
                  <div
                    key={`${event.id}-r${rowIdx}`}
                    className="text-xs px-1.5 py-0.5 truncate cursor-pointer text-white mx-0.5 leading-tight rounded-sm"
                    style={{
                      gridColumn: `${startCol + 1} / ${endCol + 1}`,
                      gridRow: rowIdx + 1,
                      backgroundColor: event.color,
                    }}
                    onClick={() => onEventClick(event)}
                  >
                    {event.title}
                  </div>
                ))
              )}
            </div>
          </div>
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
            const overlapItems = overlapByDate[key] || []

            return (
              <div
                key={key}
                className="flex-1 relative border-l cursor-pointer"
                onClick={(e) => handleColumnClick(day, e)}
              >
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

                {/* Events with overlap columns */}
                {overlapItems.map(({ event, column, totalColumns }) => {
                  const pos = getEventPosition(event)
                  if (!pos) return null
                  const colWidthPct = EVENT_WIDTH_PCT / totalColumns
                  const leftPct = (column / totalColumns) * EVENT_WIDTH_PCT
                  const gap = 2 // px gap between columns
                  return (
                    <div
                      key={event.id}
                      className="absolute rounded px-1 py-0.5 text-xs cursor-pointer overflow-hidden text-white z-[5]"
                      style={{
                        top: pos.top,
                        height: Math.max(pos.height, 18),
                        left: `calc(${leftPct}% + ${gap / 2}px)`,
                        width: `calc(${colWidthPct}% - ${gap}px)`,
                        backgroundColor: event.color,
                        opacity: 0.9,
                      }}
                      onClick={(e) => {
                        e.stopPropagation()
                        onEventClick(event)
                      }}
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
