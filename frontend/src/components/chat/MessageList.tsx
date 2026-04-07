import { Fragment, useEffect, useRef } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { MessageBubble, StreamingBubble } from './MessageBubble'
import { ToolStatusIndicator } from './ToolStatusIndicator'
import { WebSearchResultsCard } from './WebSearchResultsCard'
import { CodingJobCard } from './CodingJobCard'
import { CompactionDivider } from './CompactionDivider'
import type { ToolResult } from '@/hooks/useChat'
import type { Message, ToolResultData, CodingJobToolMetadata } from '@/types'

interface MessageListProps {
  messages: Message[]
  streamingContent: string
  isStreaming: boolean
  activeToolName?: string | null
  completedToolResults?: ToolResult[]
  conversationSummary?: string | null
}

/** Extract persisted tool results from message metadata (DB format). */
function getPersistedToolResults(message: Message): ToolResult[] | null {
  const meta = message.metadata_
  if (!meta || !Array.isArray(meta.tool_results)) return null
  return (meta.tool_results as Array<Record<string, unknown>>)
    .filter(r => (r.tool_name === 'web_search' && r.query && r.sources) || r.tool_name === 'coding_assistant')
    .map(r => ({
      toolName: r.tool_name as string,
      data: r.tool_name === 'web_search'
        ? { query: r.query, sources: r.sources } as ToolResultData
        : r as unknown as ToolResultData,
    }))
}

/** Check if a tool result is a coding job card. */
function isCodingJobResult(result: ToolResult): result is ToolResult & { data: CodingJobToolMetadata } {
  return result.toolName === 'coding_assistant' && 'job_id' in result.data
}

/** Render a tool result card (web search or coding job). */
function ToolResultCard({ result }: { result: ToolResult }) {
  if (result.toolName === 'web_search') {
    return <WebSearchResultsCard data={result.data} />
  }
  if (isCodingJobResult(result)) {
    const meta = result.data as unknown as CodingJobToolMetadata
    return (
      <CodingJobCard
        jobId={meta.job_id}
        repo={meta.repo}
        taskDescription={meta.task_description}
        question={meta.question}
      />
    )
  }
  return null
}

export function MessageList({ messages, streamingContent, isStreaming, activeToolName, completedToolResults, conversationSummary }: MessageListProps) {
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
        {conversationSummary && (
          <CompactionDivider summary={conversationSummary} />
        )}
        {messages.map((message) => {
          // Render tool results from persisted message metadata
          const savedResults = message.role === 'assistant'
            ? getPersistedToolResults(message)
            : null

          // Coding job cards render after the message text (async results);
          // other tool cards (web search) render before (inline context).
          const beforeCards = savedResults?.filter(r => !isCodingJobResult(r)) ?? []
          const afterCards = savedResults?.filter(r => isCodingJobResult(r)) ?? []

          return (
            <Fragment key={message.id}>
              {beforeCards.map((result, i) => (
                <ToolResultCard key={`before-${i}`} result={result} />
              ))}
              <MessageBubble message={message} />
              {afterCards.map((result, i) => (
                <ToolResultCard key={`after-${i}`} result={result} />
              ))}
            </Fragment>
          )
        })}
        {isStreaming && activeToolName && (
          <ToolStatusIndicator toolName={activeToolName} />
        )}
        {isStreaming && completedToolResults && completedToolResults.length > 0 && completedToolResults
          .filter(result => result.toolName !== activeToolName)
          .map((result, i) => (
            <ToolResultCard key={i} result={result} />
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
