import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut, apiPatch, apiDelete } from '@/lib/api'
import type { Todo, TodoList, TodoCreate, TodoUpdate, TodoSummary, DeleteResponse } from '@/types'

/**
 * Forces a re-render when the next open todo becomes overdue.
 * Call with the list of visible todos — the hook finds the soonest
 * future due_at among open todos and schedules a tick for that moment.
 */
export function useOverdueTick(todos: Todo[] | undefined) {
  const [, setTick] = useState(0)

  useEffect(() => {
    if (!todos?.length) return

    const now = Date.now()
    let nearest = Infinity

    for (const todo of todos) {
      if (todo.status !== 'open' || !todo.due_at) continue
      const due = new Date(
        todo.due_at.endsWith('Z') || todo.due_at.includes('+')
          ? todo.due_at
          : todo.due_at + 'Z'
      ).getTime()
      if (due > now && due < nearest) nearest = due
    }

    if (nearest === Infinity) return

    // Add 500ms buffer so the overdue check definitely passes
    const delay = nearest - now + 500
    const timer = setTimeout(() => setTick((t) => t + 1), delay)
    return () => clearTimeout(timer)
  }, [todos])
}

export function useTodos(
  page = 1,
  size = 50,
  sortBy = 'created_at',
  sortOrder = 'desc',
  status?: string,
  priority?: number,
  starred?: boolean,
  dueBefore?: string,
  dueAfter?: string
) {
  const params = new URLSearchParams({
    page: String(page),
    size: String(size),
    sort_by: sortBy,
    sort_order: sortOrder,
  })
  if (status !== undefined && status !== 'all') params.set('status', status)
  if (priority !== undefined) params.set('priority', String(priority))
  if (starred !== undefined) params.set('starred', String(starred))
  if (dueBefore) params.set('due_before', dueBefore)
  if (dueAfter) params.set('due_after', dueAfter)

  return useQuery({
    queryKey: ['todos', page, size, sortBy, sortOrder, status, priority, starred, dueBefore, dueAfter],
    queryFn: () => apiGet<TodoList>(`/todos?${params.toString()}`),
    refetchInterval: 60_000,
  })
}

export function useTodoSummary() {
  return useQuery({
    queryKey: ['todos', 'summary'],
    queryFn: () => apiGet<TodoSummary>('/todos/summary'),
    refetchInterval: 60_000,
  })
}

export function useTodoDashboard() {
  return useQuery({
    queryKey: ['todos', 'dashboard'],
    queryFn: () => apiGet<Todo[]>('/todos/dashboard'),
    refetchInterval: 60_000,
  })
}

export function useTodo(todoId: string | undefined) {
  return useQuery({
    queryKey: ['todos', todoId],
    queryFn: () => apiGet<Todo>(`/todos/${todoId}`),
    enabled: !!todoId,
  })
}

export function useCreateTodo() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: TodoCreate) => apiPost<Todo>('/todos', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['todos'] })
    },
  })
}

export function useUpdateTodo() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: TodoUpdate }) =>
      apiPut<Todo>(`/todos/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['todos'] })
    },
  })
}

export function useCompleteTodo() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => apiPatch<Todo>(`/todos/${id}/complete`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['todos'] })
    },
  })
}

export function useDeleteTodo() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => apiDelete<DeleteResponse>(`/todos/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['todos'] })
    },
  })
}
