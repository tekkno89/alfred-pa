import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPatch, apiPut, apiDelete } from '@/lib/api'
import type {
  AdminUser,
  AdminUserList,
  FeatureAccess,
  FeatureAccessUpdate,
  RoleUpdate,
} from '@/types'

export function useAdminUsers() {
  return useQuery({
    queryKey: ['admin-users'],
    queryFn: () => apiGet<AdminUserList>('/admin/users'),
  })
}

export function useUpdateUserRole() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ userId, data }: { userId: string; data: RoleUpdate }) =>
      apiPatch<AdminUser>(`/admin/users/${userId}/role`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
    },
  })
}

export function useUserFeatures(userId: string) {
  return useQuery({
    queryKey: ['admin-user-features', userId],
    queryFn: () => apiGet<FeatureAccess[]>(`/admin/users/${userId}/features`),
    enabled: !!userId,
  })
}

export function useSetFeatureAccess() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      userId,
      featureKey,
      data,
    }: {
      userId: string
      featureKey: string
      data: FeatureAccessUpdate
    }) =>
      apiPut<FeatureAccess>(
        `/admin/users/${userId}/features/${featureKey}`,
        data
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-user-features'] })
    },
  })
}

export function useDeleteFeatureAccess() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      userId,
      featureKey,
    }: {
      userId: string
      featureKey: string
    }) => apiDelete<void>(`/admin/users/${userId}/features/${featureKey}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-user-features'] })
    },
  })
}
