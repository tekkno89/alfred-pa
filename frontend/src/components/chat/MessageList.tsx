import { useEffect, useRef } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { MessageBubble, StreamingBubble } from './MessageBubble'
import type { Message } from '@/types'

interface MessageListProps {
  messages: Message[]
  streamingContent: string
  isStreaming: boolean
}

export function MessageList({ messages, streamingContent, isStreaming }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

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
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {isStreaming && streamingContent && (
          <StreamingBubble content={streamingContent} />
        )}
        {isStreaming && !streamingContent && (
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
