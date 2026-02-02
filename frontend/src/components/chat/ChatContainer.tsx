import { useState } from 'react'
import { MessageList } from './MessageList'
import { ChatInput } from './ChatInput'
import { useChat } from '@/hooks/useChat'
import type { Message } from '@/types'

interface ChatContainerProps {
  sessionId: string
  messages: Message[]
}

export function ChatContainer({ sessionId, messages }: ChatContainerProps) {
  const [error, setError] = useState<string | null>(null)

  const { streamingContent, isStreaming, sendMessage, cancelStream } = useChat({
    sessionId,
    onError: (errorMessage) => {
      setError(errorMessage)
      setTimeout(() => setError(null), 5000)
    },
  })

  return (
    <div className="h-full flex flex-col">
      {error && (
        <div className="px-4 py-2 bg-destructive/10 text-destructive text-sm">
          {error}
        </div>
      )}
      <MessageList
        messages={messages}
        streamingContent={streamingContent}
        isStreaming={isStreaming}
      />
      <ChatInput
        onSend={sendMessage}
        onCancel={cancelStream}
        isStreaming={isStreaming}
      />
    </div>
  )
}
