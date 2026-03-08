import { useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from '@/lib/api'
import type {
  CalendarListResponse,
  CalendarEventListResponse,
  CalendarEventCreateRequest,
  CalendarEventUpdateRequest,
  CalendarEvent,
  CalendarPreferenceItem,
} from '@/types'

const STALE_TIME = 5 * 60 * 1000 // 5 minutes — data shows instantly from cache

function eventsQueryKey(timeMin: string, timeMax: string) {
  return ['calendar', 'events', timeMin, timeMax] as const
}

function fetchEvents(timeMin: string, timeMax: string) {
  return apiGet<CalendarEventListResponse>(
    `/calendar/events?time_min=${encodeURIComponent(timeMin)}&time_max=${encodeURIComponent(timeMax)}`
  )
}

export function useCalendars() {
  return useQuery({
    queryKey: ['calendar', 'calendars'],
    queryFn: () => apiGet<CalendarListResponse>('/calendar/calendars'),
    staleTime: STALE_TIME,
  })
}

export function useCalendarEvents(timeMin: string, timeMax: string) {
  return useQuery({
    queryKey: eventsQueryKey(timeMin, timeMax),
    queryFn: () => fetchEvents(timeMin, timeMax),
    enabled: !!timeMin && !!timeMax,
    staleTime: STALE_TIME,
    refetchInterval: 5 * 60 * 1000,
  })
}

/**
 * Prefetch adjacent month/week ranges so navigation feels instant.
 */
export function usePrefetchAdjacentRanges(
  view: 'month' | 'week' | 'day',
  currentDate: Date,
  timeMin: string,
  timeMax: string,
) {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!timeMin || !timeMax) return

    const ranges: { min: string; max: string }[] = []

    if (view === 'month') {
      // Prefetch previous and next month
      for (const offset of [-1, 1]) {
        const d = new Date(currentDate)
        d.setMonth(d.getMonth() + offset)
        const year = d.getFullYear()
        const month = d.getMonth()
        const first = new Date(year, month, 1)
        const start = new Date(first)
        start.setDate(start.getDate() - start.getDay())
        const last = new Date(year, month + 1, 0)
        const end = new Date(last)
        end.setDate(end.getDate() + (6 - end.getDay()) + 1)
        ranges.push({ min: start.toISOString(), max: end.toISOString() })
      }
    } else if (view === 'week') {
      // Prefetch previous and next week
      for (const offset of [-7, 7]) {
        const d = new Date(currentDate)
        d.setDate(d.getDate() + offset)
        const start = new Date(d)
        start.setDate(start.getDate() - start.getDay())
        start.setHours(0, 0, 0, 0)
        const end = new Date(start)
        end.setDate(end.getDate() + 7)
        ranges.push({ min: start.toISOString(), max: end.toISOString() })
      }
    } else {
      // Prefetch previous and next day
      for (const offset of [-1, 1]) {
        const start = new Date(currentDate)
        start.setDate(start.getDate() + offset)
        start.setHours(0, 0, 0, 0)
        const end = new Date(start)
        end.setDate(end.getDate() + 1)
        ranges.push({ min: start.toISOString(), max: end.toISOString() })
      }
    }

    for (const range of ranges) {
      queryClient.prefetchQuery({
        queryKey: eventsQueryKey(range.min, range.max),
        queryFn: () => fetchEvents(range.min, range.max),
        staleTime: STALE_TIME,
      })
    }
  }, [queryClient, view, currentDate.getTime(), timeMin, timeMax])
}

export function useTodayEvents() {
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
  return useQuery({
    queryKey: ['calendar', 'events', 'today', tz],
    queryFn: () =>
      apiGet<CalendarEventListResponse>(
        `/calendar/events/today?tz=${encodeURIComponent(tz)}`
      ),
    staleTime: STALE_TIME,
    refetchInterval: 60_000,
  })
}

export function useCreateCalendarEvent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: CalendarEventCreateRequest) =>
      apiPost<CalendarEvent>('/calendar/events', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar', 'events'] })
    },
  })
}

export function useUpdateCalendarEvent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      eventId,
      data,
      calendarId,
      accountLabel,
    }: {
      eventId: string
      data: CalendarEventUpdateRequest
      calendarId: string
      accountLabel: string
    }) =>
      apiPatch<CalendarEvent>(
        `/calendar/events/${eventId}?calendar_id=${encodeURIComponent(calendarId)}&account_label=${encodeURIComponent(accountLabel)}`,
        data
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar', 'events'] })
    },
  })
}

export function useDeleteCalendarEvent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      eventId,
      calendarId,
      accountLabel,
    }: {
      eventId: string
      calendarId: string
      accountLabel: string
    }) =>
      apiDelete<void>(
        `/calendar/events/${eventId}?calendar_id=${encodeURIComponent(calendarId)}&account_label=${encodeURIComponent(accountLabel)}`
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar', 'events'] })
    },
  })
}

export function useUpdateCalendarPreferences() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (calendars: CalendarPreferenceItem[]) =>
      apiPut<CalendarListResponse>('/calendar/calendars/preferences', { calendars }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar'] })
    },
  })
}
