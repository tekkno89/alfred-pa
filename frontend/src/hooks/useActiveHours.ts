import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPut } from '@/lib/api'
import type { TriageSettings, ActiveHoursConfig, ActiveHoursBatchUpdate } from '@/types'

export function useActiveHours() {
  return useQuery({
    queryKey: ['triage', 'active-hours'],
    queryFn: () => apiGet<ActiveHoursConfig[]>('/triage/active-hours'),
  })
}

export function useUpdateActiveHours() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: ActiveHoursBatchUpdate) =>
      apiPut<ActiveHoursConfig[], ActiveHoursBatchUpdate>('/triage/active-hours', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage', 'active-hours'] })
    },
  })
}

export function useUpdateBreakthrough() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (active_hours_breakthrough: 'allow_notify_now' | 'queue_all') =>
      apiPut<TriageSettings, { active_hours_breakthrough: string }>('/triage/active-hours/breakthrough', {
        active_hours_breakthrough,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(['triage-settings'], data)
    },
  })
}
