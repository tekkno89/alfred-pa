import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut } from '@/lib/api'
import type {
  FocusEnableRequest,
  FocusSettingsResponse,
  FocusSettingsUpdate,
  FocusStatusResponse,
  PomodoroStartRequest,
} from '@/types'

export function useFocusStatus() {
  return useQuery({
    queryKey: ['focus-status'],
    queryFn: () => apiGet<FocusStatusResponse>('/focus/status'),
    refetchInterval: 30000, // Refresh every 30 seconds
  })
}

export function useFocusSettings() {
  return useQuery({
    queryKey: ['focus-settings'],
    queryFn: () => apiGet<FocusSettingsResponse>('/focus/settings'),
  })
}

export function useEnableFocus() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: FocusEnableRequest) =>
      apiPost<FocusStatusResponse>('/focus/enable', data),
    onMutate: async () => {
      // Cancel in-flight refetches so stale responses don't overwrite mutation data
      await queryClient.cancelQueries({ queryKey: ['focus-status'] })
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['focus-status'], data)
    },
  })
}

export function useDisableFocus() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => apiPost<FocusStatusResponse>('/focus/disable'),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ['focus-status'] })
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['focus-status'], data)
    },
  })
}

export function useStartPomodoro() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: PomodoroStartRequest = {}) =>
      apiPost<FocusStatusResponse>('/focus/pomodoro/start', request),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ['focus-status'] })
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['focus-status'], data)
    },
  })
}

export function useSkipPomodoroPhase() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => apiPost<FocusStatusResponse>('/focus/pomodoro/skip'),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ['focus-status'] })
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['focus-status'], data)
    },
  })
}

export function useUpdateFocusSettings() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: FocusSettingsUpdate) =>
      apiPut<FocusSettingsResponse>('/focus/settings', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['focus-settings'] })
    },
  })
}
