import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut, apiDelete } from '@/lib/api'
import type { UserRepo, UserRepoList, UserRepoCreate, UserRepoUpdate } from '@/types'

export function useUserRepos() {
  return useQuery({
    queryKey: ['user-repos'],
    queryFn: () => apiGet<UserRepoList>('/user-repos'),
  })
}

export function useAddUserRepo() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: UserRepoCreate) =>
      apiPost<UserRepo>('/user-repos', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-repos'] })
    },
  })
}

export function useUpdateUserRepo() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UserRepoUpdate }) =>
      apiPut<UserRepo>(`/user-repos/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-repos'] })
    },
  })
}

export function useDeleteUserRepo() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => apiDelete(`/user-repos/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-repos'] })
    },
  })
}
