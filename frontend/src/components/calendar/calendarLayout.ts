import type { CalendarEvent } from '@/types'

export const HOUR_HEIGHT = 60 // px per hour
export const HOURS = Array.from({ length: 24 }, (_, i) => i)
export const EVENT_WIDTH_PCT = 85

export function dateKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function getEventPosition(event: CalendarEvent): { top: number; height: number } | null {
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

export function formatHour(hour: number): string {
  if (hour === 0) return '12 AM'
  if (hour < 12) return `${hour} AM`
  if (hour === 12) return '12 PM'
  return `${hour - 12} PM`
}

export function formatEventTime(event: CalendarEvent): string {
  try {
    return new Date(event.start).toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

export type LayoutItem = { event: CalendarEvent; startCol: number; endCol: number }

export interface OverlapColumn {
  event: CalendarEvent
  column: number
  totalColumns: number
}

/**
 * Google Calendar-style column packing for overlapping timed events.
 *
 * Sorts events by start time (ties broken by longer duration first),
 * groups overlapping events, and greedily assigns column indices
 * so that concurrent events sit side-by-side.
 */
export function computeOverlapColumns(events: CalendarEvent[]): OverlapColumn[] {
  if (events.length === 0) return []

  // Parse start/end minutes for each event
  const parsed = events
    .map((event) => {
      try {
        const start = new Date(event.start)
        const end = event.end ? new Date(event.end) : new Date(start.getTime() + 60 * 60 * 1000)
        const startMin = start.getHours() * 60 + start.getMinutes()
        const endMin = end.getHours() * 60 + end.getMinutes()
        return { event, startMin, endMin: Math.max(endMin, startMin + 15) }
      } catch {
        return null
      }
    })
    .filter((p): p is { event: CalendarEvent; startMin: number; endMin: number } => p !== null)

  // Sort by start time, then longer duration first
  parsed.sort((a, b) => a.startMin - b.startMin || (b.endMin - b.startMin) - (a.endMin - a.startMin))

  // Group overlapping events and assign columns
  const result: OverlapColumn[] = []
  let groupStart = 0

  while (groupStart < parsed.length) {
    // Build a group of all mutually reachable overlapping events
    const group = [parsed[groupStart]]
    let groupEnd = parsed[groupStart].endMin
    let i = groupStart + 1

    while (i < parsed.length && parsed[i].startMin < groupEnd) {
      group.push(parsed[i])
      groupEnd = Math.max(groupEnd, parsed[i].endMin)
      i++
    }

    // Assign columns greedily within this group
    const columns: number[] = []
    const columnEnds: number[] = [] // tracks the end time of each column

    for (const item of group) {
      // Find the lowest available column
      let col = 0
      while (col < columnEnds.length && columnEnds[col] > item.startMin) {
        col++
      }
      columns.push(col)
      if (col < columnEnds.length) {
        columnEnds[col] = item.endMin
      } else {
        columnEnds.push(item.endMin)
      }
    }

    const totalColumns = columnEnds.length

    for (let j = 0; j < group.length; j++) {
      result.push({
        event: group[j].event,
        column: columns[j],
        totalColumns,
      })
    }

    groupStart = i
  }

  return result
}
