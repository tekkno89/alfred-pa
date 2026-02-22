import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from '@/lib/api'
import type { Note, NoteList, NoteCreate, NoteUpdate, DeleteResponse } from '@/types'

export function useNotes(
  page = 1,
  size = 50,
  sortBy = 'updated_at',
  archived = false,
  favorited?: boolean
) {
  const favParam = favorited !== undefined ? `&favorited=${favorited}` : ''
  return useQuery({
    queryKey: ['notes', page, size, sortBy, archived, favorited],
    queryFn: () =>
      apiGet<NoteList>(
        `/notes?page=${page}&size=${size}&sort_by=${sortBy}&archived=${archived}${favParam}`
      ),
  })
}

export function useRecentNotes() {
  return useQuery({
    queryKey: ['notes', 'recent'],
    queryFn: () => apiGet<Note[]>('/notes/recent'),
  })
}

export function useNote(noteId: string | undefined) {
  return useQuery({
    queryKey: ['notes', noteId],
    queryFn: () => apiGet<Note>(`/notes/${noteId}`),
    enabled: !!noteId,
  })
}

export function useCreateNote() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: NoteCreate) => apiPost<Note>('/notes', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes'] })
    },
  })
}

export function useUpdateNote() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: NoteUpdate }) =>
      apiPut<Note>(`/notes/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes'] })
    },
  })
}

export function useArchiveNote() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => apiPatch<Note>(`/notes/${id}/archive`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes'] })
    },
  })
}

export function useRestoreNote() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => apiPatch<Note>(`/notes/${id}/restore`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes'] })
    },
  })
}

export function useDeleteNote() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => apiDelete<DeleteResponse>(`/notes/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes'] })
    },
  })
}
