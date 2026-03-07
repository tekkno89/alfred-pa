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

export function useCalendars() {
  return useQuery({
    queryKey: ['calendar', 'calendars'],
    queryFn: () => apiGet<CalendarListResponse>('/calendar/calendars'),
    staleTime: 5 * 60 * 1000,
  })
}

export function useCalendarEvents(timeMin: string, timeMax: string) {
  return useQuery({
    queryKey: ['calendar', 'events', timeMin, timeMax],
    queryFn: () =>
      apiGet<CalendarEventListResponse>(
        `/calendar/events?time_min=${encodeURIComponent(timeMin)}&time_max=${encodeURIComponent(timeMax)}`
      ),
    enabled: !!timeMin && !!timeMax,
    refetchInterval: 5 * 60 * 1000,
  })
}

export function useTodayEvents() {
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
  return useQuery({
    queryKey: ['calendar', 'events', 'today', tz],
    queryFn: () =>
      apiGet<CalendarEventListResponse>(
        `/calendar/events/today?tz=${encodeURIComponent(tz)}`
      ),
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
