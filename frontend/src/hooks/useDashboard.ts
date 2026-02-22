import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPut, apiDelete } from '@/lib/api'
import type {
  BartDepartureResponse,
  BartStationsResponse,
  DashboardPreference,
  DashboardPreferenceList,
  DashboardPreferenceUpdate,
} from '@/types'

export function useBartDepartures(station: string, platform?: number | null) {
  const platformParam = platform ? `&platform=${platform}` : ''
  return useQuery({
    queryKey: ['bart-departures', station, platform],
    queryFn: () =>
      apiGet<BartDepartureResponse>(
        `/dashboard/bart/departures?station=${station}${platformParam}`
      ),
    refetchInterval: 60000,
    enabled: !!station,
  })
}

export function useBartStations() {
  return useQuery({
    queryKey: ['bart-stations'],
    queryFn: () => apiGet<BartStationsResponse>('/dashboard/bart/stations'),
    staleTime: 24 * 60 * 60 * 1000, // 24 hours
  })
}

export function useAvailableCards() {
  return useQuery({
    queryKey: ['available-cards'],
    queryFn: () => apiGet<string[]>('/dashboard/available-cards'),
  })
}

export function useDashboardPreferences() {
  return useQuery({
    queryKey: ['dashboard-preferences'],
    queryFn: () => apiGet<DashboardPreferenceList>('/dashboard/preferences'),
  })
}

export function useUpdateDashboardPreference() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      cardType,
      data,
    }: {
      cardType: string
      data: DashboardPreferenceUpdate
    }) => apiPut<DashboardPreference>(`/dashboard/preferences/${cardType}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard-preferences'] })
    },
  })
}

export function useRemoveDashboardCard() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (cardType: string) =>
      apiDelete<void>(`/dashboard/preferences/${cardType}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard-preferences'] })
    },
  })
}
