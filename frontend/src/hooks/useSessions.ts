import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPatch, apiDelete } from '@/lib/api'
import type { Session, SessionList, SessionCreate, SessionUpdate, SessionWithMessages, DeleteResponse } from '@/types'

export function useSessions(page = 1, size = 50) {
  return useQuery({
    queryKey: ['sessions', page, size],
    queryFn: () => apiGet<SessionList>(`/sessions?page=${page}&size=${size}`),
  })
}

export function useSession(sessionId: string | undefined) {
  return useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => apiGet<SessionWithMessages>(`/sessions/${sessionId}`),
    enabled: !!sessionId,
  })
}

export function useCreateSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: SessionCreate) => apiPost<Session>('/sessions', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}

export function useUpdateSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: SessionUpdate }) =>
      apiPatch<Session>(`/sessions/${id}`, data),
    onSuccess: (updatedSession) => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      queryClient.invalidateQueries({ queryKey: ['session', updatedSession.id] })
    },
  })
}

export function useDeleteSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (sessionId: string) => apiDelete<DeleteResponse>(`/sessions/${sessionId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}
