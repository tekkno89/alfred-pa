import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost } from '@/lib/api'
import type { CodingJob, CodingJobList, CodingJobRevisionRequest } from '@/types'

export function useCodingJob(jobId: string | undefined) {
  return useQuery({
    queryKey: ['coding-jobs', jobId],
    queryFn: () => apiGet<CodingJob>(`/coding-jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const job = query.state.data
      if (!job) return false
      // Poll while job is in a working state
      const workingStatuses = ['planning', 'implementing', 'reviewing', 'exploring']
      return workingStatuses.includes(job.status) ? 5000 : false
    },
  })
}

export function useCodingJobs(page = 1, size = 20, status?: string) {
  const params = new URLSearchParams({
    page: String(page),
    size: String(size),
  })
  if (status) params.set('status', status)

  return useQuery({
    queryKey: ['coding-jobs', 'list', page, size, status],
    queryFn: () => apiGet<CodingJobList>(`/coding-jobs?${params.toString()}`),
  })
}

export function useApprovePlan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) =>
      apiPost<CodingJob>(`/coding-jobs/${jobId}/approve-plan`, {}),
    onSuccess: (data) => {
      queryClient.setQueryData(['coding-jobs', data.id], data)
      queryClient.invalidateQueries({ queryKey: ['coding-jobs', 'list'] })
    },
  })
}

export function useApproveImpl() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) =>
      apiPost<CodingJob>(`/coding-jobs/${jobId}/approve-impl`, {}),
    onSuccess: (data) => {
      queryClient.setQueryData(['coding-jobs', data.id], data)
      queryClient.invalidateQueries({ queryKey: ['coding-jobs', 'list'] })
    },
  })
}

export function useCancelCodingJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) =>
      apiPost<CodingJob>(`/coding-jobs/${jobId}/cancel`, {}),
    onSuccess: (data) => {
      queryClient.setQueryData(['coding-jobs', data.id], data)
      queryClient.invalidateQueries({ queryKey: ['coding-jobs', 'list'] })
    },
  })
}

export function useRequestRevision() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ jobId, description }: { jobId: string; description: string }) =>
      apiPost<CodingJob>(`/coding-jobs/${jobId}/request-revision`, {
        description,
      } satisfies CodingJobRevisionRequest),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['coding-jobs'] })
    },
  })
}
