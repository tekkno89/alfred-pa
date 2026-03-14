import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from '@/lib/api'
import type {
  YouTubePlaylist,
  YouTubePlaylistListResponse,
  YouTubePlaylistCreate,
  YouTubePlaylistUpdate,
  YouTubeVideoListResponse,
  YouTubeVideoCreate,
  YouTubeVideo,
  YouTubeMetadata,
  YouTubeDashboard,
} from '@/types'

// --- Queries ---

export function useYouTubePlaylists() {
  return useQuery({
    queryKey: ['youtube', 'playlists'],
    queryFn: () => apiGet<YouTubePlaylistListResponse>('/youtube/playlists'),
  })
}

export function useYouTubeVideos(playlistId: string | null, status?: string) {
  const statusParam = status ? `?status=${status}` : ''
  return useQuery({
    queryKey: ['youtube', 'videos', playlistId, status],
    queryFn: () =>
      apiGet<YouTubeVideoListResponse>(
        `/youtube/playlists/${playlistId}/videos${statusParam}`
      ),
    enabled: !!playlistId,
  })
}

export function useFetchYouTubeMetadata(url: string) {
  return useQuery({
    queryKey: ['youtube', 'metadata', url],
    queryFn: () =>
      apiGet<YouTubeMetadata>(`/youtube/metadata?url=${encodeURIComponent(url)}`),
    enabled: !!url && url.length > 10,
  })
}

export function useYouTubeDashboard() {
  return useQuery({
    queryKey: ['youtube', 'dashboard'],
    queryFn: () => apiGet<YouTubeDashboard>('/youtube/dashboard'),
    refetchInterval: 60_000,
  })
}

// --- Mutations ---

export function useCreatePlaylist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: YouTubePlaylistCreate) =>
      apiPost<YouTubePlaylist>('/youtube/playlists', data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['youtube'], refetchType: 'all' })
    },
  })
}

export function useUpdatePlaylist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: YouTubePlaylistUpdate }) =>
      apiPut<YouTubePlaylist>(`/youtube/playlists/${id}`, data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['youtube'], refetchType: 'all' })
    },
  })
}

export function useDeletePlaylist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiDelete<void>(`/youtube/playlists/${id}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['youtube'], refetchType: 'all' })
    },
  })
}

export function useActivatePlaylist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiPatch<YouTubePlaylist>(`/youtube/playlists/${id}/activate`, {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['youtube'], refetchType: 'all' })
    },
  })
}

export function useAddVideo() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: YouTubeVideoCreate) =>
      apiPost<YouTubeVideo>('/youtube/videos', data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['youtube'], refetchType: 'all' })
    },
  })
}

export function useMarkVideoWatched() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiPatch<YouTubeVideo>(`/youtube/videos/${id}/watched`, {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['youtube'], refetchType: 'all' })
    },
  })
}

export function useMarkVideoDeleted() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiPatch<YouTubeVideo>(`/youtube/videos/${id}/deleted`, {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['youtube'], refetchType: 'all' })
    },
  })
}

export function useRestoreVideo() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiPatch<YouTubeVideo>(`/youtube/videos/${id}/restore`, {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['youtube'], refetchType: 'all' })
    },
  })
}

export function useReorderVideos() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ playlistId, videoIds }: { playlistId: string; videoIds: string[] }) =>
      apiPut<void>(`/youtube/playlists/${playlistId}/reorder`, { video_ids: videoIds }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['youtube'], refetchType: 'all' })
    },
  })
}

export function useYouTubeAllPlaylists() {
  return useQuery({
    queryKey: ['youtube', 'playlists', 'all'],
    queryFn: () =>
      apiGet<YouTubePlaylistListResponse>('/youtube/playlists?include_archived=true'),
  })
}

export function useArchivePlaylist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiPatch<YouTubePlaylist>(`/youtube/playlists/${id}/archive`, {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['youtube'], refetchType: 'all' })
    },
  })
}

export function useUnarchivePlaylist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiPatch<YouTubePlaylist>(`/youtube/playlists/${id}/unarchive`, {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['youtube'], refetchType: 'all' })
    },
  })
}
