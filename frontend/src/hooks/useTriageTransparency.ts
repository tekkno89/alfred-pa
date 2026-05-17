import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiDelete } from '@/lib/api'

export interface LearnedKeyword {
  keyword: string
  weight: number
  source_category: 'public' | 'sensitive' | 'dm'
}

export function useLearnedKeywords() {
  return useQuery({
    queryKey: ['triage', 'transparency', 'keywords'],
    queryFn: () => apiGet<{ keywords: LearnedKeyword[] }>('/triage/transparency/keywords').then((data) => data.keywords),
  })
}

export function useDeleteKeyword() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (keyword: string) =>
      apiDelete<void>(`/triage/transparency/keywords/${encodeURIComponent(keyword)}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage', 'transparency', 'keywords'] })
    },
  })
}

export function useDeleteKeywordsByCategory() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (category: string) =>
      apiDelete<{ deleted_count: number }>(
        `/triage/transparency/keywords/category/${category}`
      ).then((data) => data.deleted_count),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['triage', 'transparency', 'keywords'] })
    },
  })
}
