import { useCallback, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPatch, apiPost, apiDelete } from '@/lib/api'
import type {
  TriageSettings,
  TriageSettingsUpdate,
  MonitoredChannelList,
  MonitoredChannelCreate,
  MonitoredChannel,
  MonitoredChannelUpdate,
  ChannelMember,
  SourceExclusion,
  SourceExclusionCreate,
  ClassificationList,
  DigestResponse,
  TriageFeedbackCreate,
  TriageClassification,
  MarkReviewedRequest,
  SlackChannelInfo,
  TriageSessionStats,
  GenerateDefinitionsRequest,
  GenerateDefinitionsResponse,
  CalibrationMessage,
  CalibrateGenerateRequest,
} from '@/types'

// --- Settings ---

export function useTriageSettings() {
  return useQuery({
    queryKey: ['triage-settings'],
    queryFn: () => apiGet<TriageSettings>('/triage/settings'),
  })
}

export function useUpdateTriageSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: TriageSettingsUpdate) =>
      apiPatch<TriageSettings, TriageSettingsUpdate>('/triage/settings', data),
    onSuccess: (data) => {
      queryClient.setQueryData(['triage-settings'], data)
    },
  })
}

export function useDetectWorkspace() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiPost<TriageSettings>('/triage/settings/detect-workspace'),
    onSuccess: (data) => {
      queryClient.setQueryData(['triage-settings'], data)
    },
  })
}

// --- Monitored Channels ---

export function useMonitoredChannels() {
  return useQuery({
    queryKey: ['triage-channels'],
    queryFn: () => apiGet<MonitoredChannelList>('/triage/channels'),
  })
}

export function useAddMonitoredChannel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: MonitoredChannelCreate) =>
      apiPost<MonitoredChannel, MonitoredChannelCreate>('/triage/channels', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage-channels'] })
    },
  })
}

export function useUpdateMonitoredChannel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MonitoredChannelUpdate }) =>
      apiPatch<MonitoredChannel, MonitoredChannelUpdate>(`/triage/channels/${id}`, data),
    onMutate: async ({ id, data }) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['triage-channels'] })

      // Snapshot previous value
      const previous = queryClient.getQueryData<MonitoredChannelList>(['triage-channels'])

      // Optimistically update the cache
      if (previous) {
        queryClient.setQueryData<MonitoredChannelList>(['triage-channels'], {
          ...previous,
          channels: previous.channels.map((ch) =>
            ch.id === id ? { ...ch, ...data } : ch
          ),
        })
      }

      return { previous }
    },
    onError: (err, variables, context) => {
      // Roll back on error
      if (context?.previous) {
        queryClient.setQueryData(['triage-channels'], context.previous)
      }
    },
    onSettled: () => {
      // Always refetch to ensure cache is in sync with server
      queryClient.invalidateQueries({ queryKey: ['triage-channels'] })
    },
  })
}

export function useRemoveMonitoredChannel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiDelete<void>(`/triage/channels/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage-channels'] })
    },
  })
}

// --- Channel Members ---

export function useChannelMembers(channelId: string | null) {
  return useQuery({
    queryKey: ['triage-channel-members', channelId],
    queryFn: () => apiGet<ChannelMember[]>(`/triage/channels/${channelId}/members`),
    enabled: !!channelId,
  })
}

// --- Auto-Enroll ---

export function useAutoEnrollChannels() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiPost<{ enrolled_count: number; removed_count: number; total_monitored: number }>('/triage/channels/auto-enroll'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage-channels'] })
    },
  })
}

// --- Source Exclusions ---

export function useSourceExclusions(channelId: string) {
  return useQuery({
    queryKey: ['triage-exclusions', channelId],
    queryFn: () => apiGet<SourceExclusion[]>(`/triage/channels/${channelId}/exclusions`),
    enabled: !!channelId,
  })
}

export function useAddSourceExclusion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ channelId, data }: { channelId: string; data: SourceExclusionCreate }) =>
      apiPost<SourceExclusion, SourceExclusionCreate>(`/triage/channels/${channelId}/exclusions`, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['triage-exclusions', variables.channelId] })
    },
  })
}

export function useRemoveSourceExclusion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ channelId, exclusionId }: { channelId: string; exclusionId: string }) =>
      apiDelete<void>(`/triage/channels/${channelId}/exclusions/${exclusionId}`),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['triage-exclusions', variables.channelId] })
    },
  })
}

// --- Available Slack Channels ---

export function useAvailableSlackChannels() {
  return useQuery({
    queryKey: ['triage-slack-channels'],
    queryFn: () => apiGet<SlackChannelInfo[]>('/triage/slack-channels'),
    staleTime: 5 * 60 * 1000, // 5 minutes — served from DB cache
  })
}

export function useRefreshSlackChannels() {
  const queryClient = useQueryClient()
  const [refreshing, setRefreshing] = useState(false)

  // Call this when a notification event arrives so the hook can react
  const onNotification = useCallback(
    (event: { type: string }) => {
      if (event.type === 'slack_channels.refreshed' && refreshing) {
        setRefreshing(false)
        queryClient.invalidateQueries({ queryKey: ['triage-slack-channels'] })
      }
    },
    [queryClient, refreshing],
  )

  // Safety timeout — if SSE event never arrives, re-enable after 30s
  useEffect(() => {
    if (!refreshing) return
    const timer = setTimeout(() => {
      setRefreshing(false)
      queryClient.invalidateQueries({ queryKey: ['triage-slack-channels'] })
    }, 30_000)
    return () => clearTimeout(timer)
  }, [refreshing, queryClient])

  const mutation = useMutation({
    mutationFn: () => apiPost<{ status: string }>('/triage/slack-channels/refresh'),
    onSuccess: () => setRefreshing(true),
  })

  return { ...mutation, refreshing, onNotification }
}

// --- Classifications ---

export function useClassifications(params?: {
  priority?: string
  channel_id?: string
  reviewed?: boolean
  hide_active_digest?: boolean
  limit?: number
  offset?: number
}) {
  const searchParams = new URLSearchParams()
  if (params?.priority) searchParams.set('priority', params.priority)
  if (params?.channel_id) searchParams.set('channel_id', params.channel_id)
  if (params?.reviewed !== undefined) searchParams.set('reviewed', String(params.reviewed))
  if (params?.hide_active_digest !== undefined) searchParams.set('hide_active_digest', String(params.hide_active_digest))
  if (params?.limit) searchParams.set('limit', String(params.limit))
  if (params?.offset) searchParams.set('offset', String(params.offset))
  const qs = searchParams.toString()
  const path = `/triage/classifications${qs ? `?${qs}` : ''}`

  return useQuery({
    queryKey: ['triage-classifications', params],
    queryFn: () => apiGet<ClassificationList>(path),
  })
}

export function useSessionDigest(sessionId: string) {
  return useQuery({
    queryKey: ['triage-digest', sessionId],
    queryFn: () => apiGet<DigestResponse>(`/triage/digest/${sessionId}`),
    enabled: !!sessionId,
  })
}

export function useLatestDigest() {
  return useQuery({
    queryKey: ['triage-digest-latest'],
    queryFn: () => apiGet<DigestResponse>('/triage/digest/latest'),
  })
}

// --- Feedback ---

export function useSubmitFeedback() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: TriageFeedbackCreate) =>
      apiPost<{ status: string }, TriageFeedbackCreate>('/triage/analytics/feedback', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage-classifications'] })
    },
  })
}

// --- Review Status ---

export function useMarkReviewed() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: MarkReviewedRequest) =>
      apiPatch<{ updated: number }, MarkReviewedRequest>('/triage/classifications/reviewed', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage-classifications'] })
      queryClient.invalidateQueries({ queryKey: ['triage-session-stats'] })
    },
  })
}

// --- Digest Children ---

export function useDigestChildren(classificationId: string | null) {
  return useQuery({
    queryKey: ['triage-digest-children', classificationId],
    queryFn: () =>
      apiGet<TriageClassification[]>(`/triage/classifications/${classificationId}/digest-children`),
    enabled: !!classificationId,
  })
}

// --- Analytics ---

export function useTriageSessionStats() {
  return useQuery({
    queryKey: ['triage-session-stats'],
    queryFn: () => apiGet<TriageSessionStats>('/triage/analytics/session-stats'),
  })
}

// --- AI Wizard ---

export function useGenerateDefinitions() {
  return useMutation({
    mutationFn: (data: GenerateDefinitionsRequest) =>
      apiPost<GenerateDefinitionsResponse, GenerateDefinitionsRequest>(
        '/triage/settings/generate-definitions',
        data
      ),
  })
}

// --- Calibration ---

export function useSampleCalibrationMessages() {
  return useMutation({
    mutationFn: (data?: { exclude_message_ids?: string[] }) =>
      apiPost<CalibrationMessage[]>('/triage/settings/calibrate/sample-messages', data || {}),
  })
}

export function useGenerateDefinitionsFromCalibration() {
  return useMutation({
    mutationFn: (data: CalibrateGenerateRequest) =>
      apiPost<GenerateDefinitionsResponse, CalibrateGenerateRequest>(
        '/triage/settings/calibrate/generate',
        data
      ),
  })
}
