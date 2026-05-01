import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet } from '@/lib/api'
import type {
  ConversationSummary,
  ConversationSummaryList,
  ConversationMessageList,
} from '@/types'

export function useDigestConversations(
  digestId: string | null,
  options?: { priority?: string }
) {
  const searchParams = new URLSearchParams()
  searchParams.set('limit', '100')
  if (options?.priority) {
    searchParams.set('priority', options.priority)
  }
  const qs = searchParams.toString()
  const path = `/triage/digests/${digestId}/conversations?${qs}`

  return useQuery({
    queryKey: ['digest-conversations', digestId, options?.priority],
    queryFn: () => apiGet<ConversationSummaryList>(path),
    enabled: !!digestId,
  })
}

export function useConversation(conversationId: string | null) {
  return useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () =>
      apiGet<ConversationSummary>(`/triage/conversations/${conversationId}`),
    enabled: !!conversationId,
  })
}

export function useConversationMessages(
  conversationId: string | null,
  options?: { limit?: number; offset?: number }
) {
  const limit = options?.limit ?? 50
  const offset = options?.offset ?? 0
  const searchParams = new URLSearchParams()
  searchParams.set('limit', String(limit))
  searchParams.set('offset', String(offset))
  const qs = searchParams.toString()
  const path = `/triage/conversations/${conversationId}/messages?${qs}`

  return useQuery({
    queryKey: ['conversation-messages', conversationId, limit, offset],
    queryFn: () => apiGet<ConversationMessageList>(path),
    enabled: !!conversationId,
  })
}

export function useInvalidateConversations() {
  const queryClient = useQueryClient()

  return {
    invalidateDigest: (digestId: string) => {
      queryClient.invalidateQueries({ queryKey: ['digest-conversations', digestId] })
    },
    invalidateConversation: (conversationId: string) => {
      queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] })
      queryClient.invalidateQueries({ queryKey: ['conversation-messages', conversationId] })
    },
  }
}
