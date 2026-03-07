import { useState, useMemo, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Plus, PanelRight, CalendarDays } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useCalendarEvents } from '@/hooks/useCalendar'
import { MonthlyView } from '@/components/calendar/MonthlyView'
import { WeeklyView } from '@/components/calendar/WeeklyView'
import { CalendarSidebar } from '@/components/calendar/CalendarSidebar'
import { EventDetailDialog } from '@/components/calendar/EventDetailDialog'
import { EventCreateDialog } from '@/components/calendar/EventCreateDialog'
import type { CalendarEvent } from '@/types'

type ViewMode = 'month' | 'week'

function getMonthRange(date: Date): { timeMin: string; timeMax: string } {
  const year = date.getFullYear()
  const month = date.getMonth()
  // Include padding days from prev/next month
  const firstDay = new Date(year, month, 1)
  const start = new Date(firstDay)
  start.setDate(start.getDate() - start.getDay())

  const lastDay = new Date(year, month + 1, 0)
  const end = new Date(lastDay)
  end.setDate(end.getDate() + (6 - end.getDay()) + 1)

  return {
    timeMin: start.toISOString(),
    timeMax: end.toISOString(),
  }
}

function getWeekRange(date: Date): { timeMin: string; timeMax: string } {
  const start = new Date(date)
  start.setDate(start.getDate() - start.getDay())
  start.setHours(0, 0, 0, 0)

  const end = new Date(start)
  end.setDate(end.getDate() + 7)

  return {
    timeMin: start.toISOString(),
    timeMax: end.toISOString(),
  }
}

export function CalendarPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [view, setView] = useState<ViewMode>((searchParams.get('view') as ViewMode) || 'month')
  const [currentDate, setCurrentDate] = useState(new Date())
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [createDate, setCreateDate] = useState<Date | undefined>()
  const [editEvent, setEditEvent] = useState<CalendarEvent | null>(null)

  // Handle URL params
  useEffect(() => {
    if (searchParams.get('create') === 'true') {
      setCreateOpen(true)
      searchParams.delete('create')
      setSearchParams(searchParams, { replace: true })
    }
  }, [searchParams, setSearchParams])

  const { timeMin, timeMax } = useMemo(
    () => (view === 'month' ? getMonthRange(currentDate) : getWeekRange(currentDate)),
    [currentDate, view]
  )

  const { data, isLoading } = useCalendarEvents(timeMin, timeMax)
  const events = data?.events ?? []

  const navigate = useCallback(
    (direction: number) => {
      setCurrentDate((prev) => {
        const next = new Date(prev)
        if (view === 'month') {
          next.setMonth(next.getMonth() + direction)
        } else {
          next.setDate(next.getDate() + direction * 7)
        }
        return next
      })
    },
    [view]
  )

  const goToday = () => setCurrentDate(new Date())

  const handleEventClick = (event: CalendarEvent) => {
    setSelectedEvent(event)
    setDetailOpen(true)
  }

  const handleDayClick = (date: Date) => {
    setCreateDate(date)
    setCreateOpen(true)
  }

  const handleEdit = (event: CalendarEvent) => {
    setEditEvent(event)
    setCreateOpen(true)
  }

  const headerTitle = useMemo(() => {
    if (view === 'month') {
      return currentDate.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
    }
    const start = new Date(currentDate)
    start.setDate(start.getDate() - start.getDay())
    const end = new Date(start)
    end.setDate(end.getDate() + 6)

    if (start.getMonth() === end.getMonth()) {
      return `${start.toLocaleDateString(undefined, { month: 'long' })} ${start.getDate()} – ${end.getDate()}, ${start.getFullYear()}`
    }
    return `${start.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} – ${end.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}`
  }, [currentDate, view])

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 p-3 border-b shrink-0">
        <CalendarDays className="h-5 w-5 text-muted-foreground" />
        <h1 className="text-lg font-semibold mr-2">{headerTitle}</h1>

        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => navigate(-1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="sm" className="h-8" onClick={goToday}>
            Today
          </Button>
          <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => navigate(1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex items-center gap-1 ml-2 border rounded-md">
          <Button
            variant={view === 'month' ? 'secondary' : 'ghost'}
            size="sm"
            className="h-7 rounded-r-none"
            onClick={() => setView('month')}
          >
            Month
          </Button>
          <Button
            variant={view === 'week' ? 'secondary' : 'ghost'}
            size="sm"
            className="h-7 rounded-l-none"
            onClick={() => setView('week')}
          >
            Week
          </Button>
        </div>

        <div className="flex-1" />

        <Button size="sm" onClick={() => { setEditEvent(null); setCreateDate(undefined); setCreateOpen(true) }}>
          <Plus className="h-4 w-4 mr-1" />
          New Event
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => setSidebarOpen(!sidebarOpen)}
          title={sidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
        >
          <PanelRight className="h-4 w-4" />
        </Button>
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 flex flex-col overflow-hidden">
          {isLoading ? (
            <div className="flex-1 flex items-center justify-center text-muted-foreground">
              Loading events...
            </div>
          ) : view === 'month' ? (
            <MonthlyView
              currentDate={currentDate}
              events={events}
              onEventClick={handleEventClick}
              onDayClick={handleDayClick}
            />
          ) : (
            <WeeklyView
              currentDate={currentDate}
              events={events}
              onEventClick={handleEventClick}
            />
          )}
        </div>

        <CalendarSidebar collapsed={!sidebarOpen} />
      </div>

      {/* Dialogs */}
      <EventDetailDialog
        event={selectedEvent}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        onEdit={handleEdit}
      />

      <EventCreateDialog
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open)
          if (!open) setEditEvent(null)
        }}
        initialDate={createDate}
        editEvent={editEvent}
      />
    </div>
  )
}
