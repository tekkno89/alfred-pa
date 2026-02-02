import type { StreamEvent } from '@/types'

export function parseSSELine(line: string): StreamEvent | null {
  if (!line.startsWith('data: ')) {
    return null
  }

  try {
    return JSON.parse(line.slice(6)) as StreamEvent
  } catch {
    return null
  }
}

export function createSSEParser(
  onToken: (content: string) => void,
  onDone: (messageId?: string) => void,
  onError: (error: string) => void
) {
  return (event: StreamEvent) => {
    switch (event.type) {
      case 'token':
        if (event.content) {
          onToken(event.content)
        }
        break
      case 'done':
        onDone(event.message_id)
        break
      case 'error':
        onError(event.content || 'Unknown error')
        break
    }
  }
}
