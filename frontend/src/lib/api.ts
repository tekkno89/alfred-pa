import { useAuthStore } from './auth'
import type { ApiError } from '@/types'

const API_BASE_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000') + '/api'

export class ApiRequestError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail)
    this.name = 'ApiRequestError'
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = 'An error occurred'
    try {
      const error: ApiError = await response.json()
      detail = error.detail || detail
    } catch {
      detail = response.statusText
    }
    throw new ApiRequestError(response.status, detail)
  }

  // Handle empty responses
  const text = await response.text()
  if (!text) {
    return {} as T
  }
  return JSON.parse(text)
}

function getAuthHeaders(): HeadersInit {
  const token = useAuthStore.getState().token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  })
  return handleResponse<T>(response)
}

export async function apiPost<T, D = unknown>(path: string, data?: D): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: data ? JSON.stringify(data) : undefined,
  })
  return handleResponse<T>(response)
}

export async function apiPut<T, D = unknown>(path: string, data: D): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(data),
  })
  return handleResponse<T>(response)
}

export async function apiPatch<T, D = unknown>(path: string, data: D): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(data),
  })
  return handleResponse<T>(response)
}

export async function apiDelete<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  })
  return handleResponse<T>(response)
}

// SSE streaming fetch for chat
export function apiStreamPost(
  path: string,
  data: unknown,
  onEvent: (event: { type: string; content?: string; message_id?: string }) => void,
  onError: (error: Error) => void,
  onComplete: () => void
): AbortController {
  const controller = new AbortController()

  fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(data),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        let detail = 'An error occurred'
        try {
          const error = await response.json()
          detail = error.detail || detail
        } catch {
          detail = response.statusText
        }
        throw new ApiRequestError(response.status, detail)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No response body')
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const eventData = JSON.parse(line.slice(6))
              onEvent(eventData)
            } catch {
              // Skip invalid JSON
            }
          }
        }
      }

      // Process remaining buffer
      if (buffer.startsWith('data: ')) {
        try {
          const eventData = JSON.parse(buffer.slice(6))
          onEvent(eventData)
        } catch {
          // Skip invalid JSON
        }
      }

      onComplete()
    })
    .catch((error) => {
      if (error.name !== 'AbortError') {
        onError(error)
      }
    })

  return controller
}
