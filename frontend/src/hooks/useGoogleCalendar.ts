import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiDelete } from '@/lib/api'
import type { GoogleCalendarConnectionList } from '@/types'

export function useGoogleCalendarConnections() {
  return useQuery({
    queryKey: ['google-calendar-connections'],
    queryFn: () =>
      apiGet<GoogleCalendarConnectionList>('/google-calendar/connections'),
  })
}

export function useRemoveGoogleCalendarConnection() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (connectionId: string) =>
      apiDelete(`/google-calendar/connections/${connectionId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['google-calendar-connections'],
      })
    },
  })
}

export function useConnectGoogleCalendarOAuth() {
  return useMutation({
    mutationFn: async ({ accountLabel }: { accountLabel: string }) => {
      const params = new URLSearchParams()
      if (accountLabel) params.set('account_label', accountLabel)
      const qs = params.toString()
      const response = await apiGet<{ url: string }>(
        `/google-calendar/oauth/url${qs ? `?${qs}` : ''}`
      )
      window.location.href = response.url
    },
  })
}
