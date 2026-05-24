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
  SourceRule,
  SourceRuleCreate,
  ClassificationList,
  DigestResponse,
  TriageFeedbackCreate,
  TriageClassification,
  MarkReviewedRequest,
  MarkAllReviewedRequest,
  SlackChannelInfo,
  TriageSessionStats,
  GenerateDefinitionsRequest,
  GenerateDefinitionsResponse,
  CalibrationMessage,
  CalibrateGenerateRequest,
  FetchMessageByLinkRequest,
  AwayModeToggleRequest,
  AwayModeToggleResponse,
  AwayModeConfigureRequest,
  AdaptiveWindowList,
  AdaptiveWindowResetResponse,
  WizardRoleRequest,
  WizardQuestionResponse,
  WizardDefinitionRequest,
  WizardDefinitionResponse,
  FetchMessagesRequest,
  FetchMessagesResponse,
  WizardGoalsRequest,
  WizardGoalsResponse,
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
    onError: (_err, _variables, context) => {
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

// --- Source Rules ---

export function useSourceRules(channelId: string) {
  return useQuery({
    queryKey: ['triage-rules', channelId],
    queryFn: () => apiGet<SourceRule[]>(`/triage/channels/${channelId}/rules`),
    enabled: !!channelId,
  })
}

export function useAddSourceRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ channelId, data }: { channelId: string; data: SourceRuleCreate }) =>
      apiPost<SourceRule, SourceRuleCreate>(`/triage/channels/${channelId}/rules`, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['triage-rules', variables.channelId] })
    },
  })
}

export function useRemoveSourceRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ channelId, ruleId }: { channelId: string; ruleId: string }) =>
      apiDelete<void>(`/triage/channels/${channelId}/rules/${ruleId}`),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['triage-rules', variables.channelId] })
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

export type TriageFilter = 'needs_attention' | 'p0' | 'focus' | 'scheduled' | 'review' | 'reviewed'

export function useClassifications(params?: {
  filter?: TriageFilter
  limit?: number
  offset?: number
}) {
  const filter = params?.filter ?? 'needs_attention'
  const searchParams = new URLSearchParams()
  searchParams.set('filter', filter)
  if (params?.limit) searchParams.set('limit', String(params.limit))
  if (params?.offset) searchParams.set('offset', String(params.offset))
  const qs = searchParams.toString()
  const path = `/triage/classifications?${qs}`

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

export function useMarkAllReviewed() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: MarkAllReviewedRequest) =>
      apiPost<{ updated: number }, MarkAllReviewedRequest>(
        '/triage/classifications/mark-all-reviewed',
        data
      ),
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

export function useFetchMessageByLink() {
  return useMutation({
    mutationFn: (data: FetchMessageByLinkRequest) =>
      apiPost<CalibrationMessage, FetchMessageByLinkRequest>(
        '/triage/settings/calibrate/fetch-by-link',
        data
      ),
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

// --- Away Mode ---

export function useToggleAwayMode() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: AwayModeToggleRequest) =>
      apiPost<AwayModeToggleResponse, AwayModeToggleRequest>(
        '/triage/away-mode/toggle',
        data
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(['triage-settings'], (old: TriageSettings | undefined) =>
        old ? { ...old, away_mode_enabled: data.enabled } : old
      )
    },
  })
}

export function useConfigureAwayMode() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: AwayModeConfigureRequest) =>
      apiPost<TriageSettings, AwayModeConfigureRequest>(
        '/triage/away-mode/configure',
        data
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(['triage-settings'], data)
    },
  })
}

// --- Adaptive Windows ---

export function useAdaptiveWindows() {
  return useQuery({
    queryKey: ['triage-adaptive-windows'],
    queryFn: () => apiGet<AdaptiveWindowList>('/triage/adaptive-windows'),
  })
}

export function useResetAdaptiveWindow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (messageTypeName: string) =>
      apiPost<AdaptiveWindowResetResponse>(
        `/triage/adaptive-windows/${encodeURIComponent(messageTypeName)}/reset`
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage-adaptive-windows'] })
    },
  })
}

// --- New Wizard API ---

export function useGenerateWizardQuestions() {
  return useMutation({
    mutationFn: (data: WizardRoleRequest) =>
      apiPost<WizardQuestionResponse, WizardRoleRequest>(
        '/triage/wizard/generate-questions',
        data
      ),
  })
}

export function useGenerateWizardDefinitions() {
  return useMutation({
    mutationFn: (data: WizardDefinitionRequest) =>
      apiPost<WizardDefinitionResponse, WizardDefinitionRequest>(
        '/triage/wizard/generate-definitions',
        data
      ),
  })
}

export function useFetchWizardMessages() {
  return useMutation({
    mutationFn: (data: FetchMessagesRequest) =>
      apiPost<FetchMessagesResponse, FetchMessagesRequest>(
        '/triage/wizard/fetch-messages',
        data
      ),
  })
}

export function useGenerateWizardGoals() {
  return useMutation({
    mutationFn: (data: WizardGoalsRequest) =>
      apiPost<WizardGoalsResponse, WizardGoalsRequest>(
        '/triage/wizard/generate-goals',
        data
      ),
  })
}
