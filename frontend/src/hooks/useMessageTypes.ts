import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'
import type { MessageType, ChannelTypeRule, MessageTypeCreate, ChannelTypeRuleCreate } from '@/types'

export function useMessageTypes(includeArchived = false) {
  return useQuery({
    queryKey: ['triage', 'message-types', { includeArchived }],
    queryFn: () => {
      const params = includeArchived ? '?include_archived=true' : ''
      return apiGet<MessageType[]>(`/triage/message-types${params}`)
    },
  })
}

export function useCreateMessageType() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: MessageTypeCreate) =>
      apiPost<MessageType, MessageTypeCreate>('/triage/message-types', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage', 'message-types'] })
    },
  })
}

export function useUpdateMessageType() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { type_name?: string; type_definition?: string } }) =>
      apiPut<MessageType, typeof data>(`/triage/message-types/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage', 'message-types'] })
    },
  })
}

export function useArchiveMessageType() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiDelete<void>(`/triage/message-types/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage', 'message-types'] })
    },
  })
}

export function useChannelTypeRules(channelId: string | null) {
  return useQuery({
    queryKey: ['triage', 'channel-type-rules', channelId],
    queryFn: () => apiGet<ChannelTypeRule[]>(`/triage/channels/${channelId}/type-rules`),
    enabled: !!channelId,
  })
}

export function useCreateChannelTypeRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ channelId, data }: { channelId: string; data: ChannelTypeRuleCreate }) =>
      apiPost<ChannelTypeRule, ChannelTypeRuleCreate>(
        `/triage/channels/${channelId}/type-rules`,
        data
      ),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['triage', 'channel-type-rules', variables.channelId],
      })
    },
  })
}

export function useDeleteChannelTypeRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ channelId, ruleId }: { channelId: string; ruleId: string }) =>
      apiDelete<void>(`/triage/channels/${channelId}/type-rules/${ruleId}`),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['triage', 'channel-type-rules', variables.channelId],
      })
    },
  })
}

export function useMessageTypeSuggestions(role: string | null) {
  return useQuery({
    queryKey: ['triage', 'message-type-suggestions', role],
    queryFn: () =>
      apiGet<{ type_name: string; type_definition: string; confidence: number }[]>(
        `/triage/message-types/suggestions?role=${encodeURIComponent(role!)}`
      ),
    enabled: !!role,
  })
}
