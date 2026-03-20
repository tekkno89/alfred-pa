import { useState, useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { MessageList } from './MessageList'
import { ChatInput } from './ChatInput'
import { ContextUsageBar } from './ContextUsageBar'
import { useChat } from '@/hooks/useChat'
import { useCompactSession } from '@/hooks/useSessions'
import type { ContextUsage, Message } from '@/types'

interface ChatContainerProps {
  sessionId: string
  messages: Message[]
  initialContextUsage?: ContextUsage | null
  conversationSummary?: string | null
}

interface LocationState {
  initialMessage?: string
}

export function ChatContainer({ sessionId, messages, initialContextUsage, conversationSummary }: ChatContainerProps) {
  const [error, setError] = useState<string | null>(null)
  const location = useLocation()
  const initialMessageSentRef = useRef(false)

  const { streamingContent, isStreaming, activeToolName, completedToolResults, contextUsage: streamContextUsage, sendMessage, cancelStream } = useChat({
    sessionId,
    onError: (errorMessage) => {
      setError(errorMessage)
      setTimeout(() => setError(null), 5000)
    },
  })

  const compactMutation = useCompactSession()

  // Use streaming context usage if available, otherwise fall back to initial
  const activeContextUsage = streamContextUsage || initialContextUsage || null

  useEffect(() => {
    const state = location.state as LocationState | null
    if (state?.initialMessage && !initialMessageSentRef.current) {
      initialMessageSentRef.current = true
      // Clear the state to prevent re-sending on refresh
      window.history.replaceState({}, document.title)
      sendMessage(state.initialMessage)
    }
  }, [location.state, sessionId]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleCompact = () => {
    compactMutation.mutate(sessionId)
  }

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
        activeToolName={activeToolName}
        completedToolResults={completedToolResults}
        conversationSummary={conversationSummary}
      />
      {activeContextUsage && (
        <ContextUsageBar
          contextUsage={activeContextUsage}
          onCompact={handleCompact}
          isCompacting={compactMutation.isPending}
        />
      )}
      <ChatInput
        onSend={sendMessage}
        onCancel={cancelStream}
        isStreaming={isStreaming}
        autoFocus
      />
    </div>
  )
}
