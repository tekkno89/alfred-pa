import { Fragment, useEffect, useRef } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { MessageBubble, StreamingBubble } from './MessageBubble'
import { ToolStatusIndicator } from './ToolStatusIndicator'
import { WebSearchResultsCard } from './WebSearchResultsCard'
import type { ToolResult } from '@/hooks/useChat'
import type { Message, ToolResultData } from '@/types'

interface MessageListProps {
  messages: Message[]
  streamingContent: string
  isStreaming: boolean
  activeToolName?: string | null
  completedToolResults?: ToolResult[]
}

/** Extract persisted tool results from message metadata (DB format). */
function getPersistedToolResults(message: Message): ToolResult[] | null {
  const meta = message.metadata_
  if (!meta || !Array.isArray(meta.tool_results)) return null
  return (meta.tool_results as Array<Record<string, unknown>>)
    .filter(r => r.tool_name === 'web_search' && r.query && r.sources)
    .map(r => ({
      toolName: r.tool_name as string,
      data: { query: r.query, sources: r.sources } as ToolResultData,
    }))
}

export function MessageList({ messages, streamingContent, isStreaming, activeToolName, completedToolResults }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent, activeToolName, completedToolResults])

  if (messages.length === 0 && !isStreaming) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center text-muted-foreground">
          <p className="text-lg font-medium">Start a conversation</p>
          <p className="text-sm">Send a message to begin chatting with Alfred</p>
        </div>
      </div>
    )
  }

  return (
    <ScrollArea className="flex-1 px-4">
      <div className="max-w-3xl mx-auto py-4">
        {messages.map((message) => {
          // Render tool results from persisted message metadata
          const savedResults = message.role === 'assistant'
            ? getPersistedToolResults(message)
            : null

          return (
            <Fragment key={message.id}>
              {savedResults && savedResults.map((result, i) => (
                <WebSearchResultsCard key={i} data={result.data} />
              ))}
              <MessageBubble message={message} />
            </Fragment>
          )
        })}
        {isStreaming && activeToolName && (
          <ToolStatusIndicator toolName={activeToolName} />
        )}
        {isStreaming && completedToolResults && completedToolResults.length > 0 && completedToolResults
          .filter(result => result.toolName !== activeToolName)
          .map((result, i) => (
            result.toolName === 'web_search' && (
              <WebSearchResultsCard key={i} data={result.data} />
            )
          ))}
        {isStreaming && streamingContent && (
          <StreamingBubble content={streamingContent} />
        )}
        {isStreaming && !streamingContent && !activeToolName && (
          <div className="flex gap-3 py-4">
            <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center">
              <div className="h-4 w-4 border-2 border-muted-foreground/50 border-t-transparent rounded-full animate-spin" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  )
}
