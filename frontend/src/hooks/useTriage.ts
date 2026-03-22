import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPatch, apiPost, apiDelete } from '@/lib/api'
import type {
  TriageSettings,
  TriageSettingsUpdate,
  MonitoredChannelList,
  MonitoredChannelCreate,
  MonitoredChannel,
  MonitoredChannelUpdate,
  KeywordRule,
  KeywordRuleCreate,
  SourceExclusion,
  SourceExclusionCreate,
  ClassificationList,
  DigestResponse,
  TriageFeedbackCreate,
  TriageClassification,
  MarkReviewedRequest,
  SlackChannelInfo,
  TriageSessionStats,
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
    onSuccess: () => {
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

// --- Keyword Rules ---

export function useKeywordRules(channelId: string) {
  return useQuery({
    queryKey: ['triage-rules', channelId],
    queryFn: () => apiGet<KeywordRule[]>(`/triage/channels/${channelId}/rules`),
    enabled: !!channelId,
  })
}

export function useAddKeywordRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ channelId, data }: { channelId: string; data: KeywordRuleCreate }) =>
      apiPost<KeywordRule, KeywordRuleCreate>(`/triage/channels/${channelId}/rules`, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['triage-rules', variables.channelId] })
    },
  })
}

export function useRemoveKeywordRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ channelId, ruleId }: { channelId: string; ruleId: string }) =>
      apiDelete<void>(`/triage/channels/${channelId}/rules/${ruleId}`),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['triage-rules', variables.channelId] })
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
    staleTime: 60000,
  })
}

// --- Classifications ---

export function useClassifications(params?: {
  urgency?: string
  channel_id?: string
  reviewed?: boolean
  hide_active_digest?: boolean
  limit?: number
  offset?: number
}) {
  const searchParams = new URLSearchParams()
  if (params?.urgency) searchParams.set('urgency', params.urgency)
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
