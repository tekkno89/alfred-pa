import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'
import type { Memory, MemoryList, MemoryCreate, MemoryUpdate, MemoryType, DeleteResponse } from '@/types'

export function useMemories(page = 1, size = 50, type?: MemoryType) {
  const typeParam = type ? `&type=${type}` : ''
  return useQuery({
    queryKey: ['memories', page, size, type],
    queryFn: () => apiGet<MemoryList>(`/memories?page=${page}&size=${size}${typeParam}`),
  })
}

export function useCreateMemory() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: MemoryCreate) => apiPost<Memory>('/memories', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] })
    },
  })
}

export function useUpdateMemory() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MemoryUpdate }) =>
      apiPut<Memory>(`/memories/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] })
    },
  })
}

export function useDeleteMemory() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => apiDelete<DeleteResponse>(`/memories/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] })
    },
  })
}
