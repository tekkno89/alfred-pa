import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiDelete } from '@/lib/api'
import type {
  GitHubConnectionList,
  GitHubConnection,
  GitHubPATRequest,
  GitHubAppConfigList,
  GitHubAppConfig,
  GitHubAppConfigCreateRequest,
} from '@/types'

export function useGitHubConnections() {
  return useQuery({
    queryKey: ['github-connections'],
    queryFn: () => apiGet<GitHubConnectionList>('/github/connections'),
  })
}

export function useAddGitHubPAT() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: GitHubPATRequest) =>
      apiPost<GitHubConnection>('/github/connections/pat', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['github-connections'] })
    },
  })
}

export function useRemoveGitHubConnection() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (connectionId: string) =>
      apiDelete(`/github/connections/${connectionId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['github-connections'] })
    },
  })
}

export function useConnectGitHubOAuth() {
  return useMutation({
    mutationFn: async ({
      accountLabel,
      appConfigId,
    }: { accountLabel?: string; appConfigId?: string } = {}) => {
      const params = new URLSearchParams()
      if (accountLabel) params.set('account_label', accountLabel)
      if (appConfigId) params.set('app_config_id', appConfigId)
      const qs = params.toString()
      const response = await apiGet<{ url: string }>(
        `/github/oauth/url${qs ? `?${qs}` : ''}`
      )
      window.location.href = response.url
    },
  })
}

// --- App Config Hooks ---

export function useGitHubAppConfigs() {
  return useQuery({
    queryKey: ['github-app-configs'],
    queryFn: () => apiGet<GitHubAppConfigList>('/github/app-configs'),
  })
}

export function useCreateGitHubAppConfig() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: GitHubAppConfigCreateRequest) =>
      apiPost<GitHubAppConfig>('/github/app-configs', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['github-app-configs'] })
    },
  })
}

export function useDeleteGitHubAppConfig() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (configId: string) =>
      apiDelete(`/github/app-configs/${configId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['github-app-configs'] })
      queryClient.invalidateQueries({ queryKey: ['github-connections'] })
    },
  })
}
