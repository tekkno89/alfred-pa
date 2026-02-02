import { cn } from '@/lib/utils'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Brain, User } from 'lucide-react'
import type { Message } from '@/types'

interface MessageBubbleProps {
  message: Message
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <div
      className={cn(
        'flex gap-3 py-4',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback className={cn(isUser ? 'bg-primary' : 'bg-muted')}>
          {isUser ? (
            <User className="h-4 w-4 text-primary-foreground" />
          ) : (
            <Brain className="h-4 w-4" />
          )}
        </AvatarFallback>
      </Avatar>
      <div
        className={cn(
          'rounded-lg px-4 py-2 max-w-[80%]',
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted'
        )}
      >
        <p className="whitespace-pre-wrap break-words text-sm">
          {message.content}
        </p>
      </div>
    </div>
  )
}

interface StreamingBubbleProps {
  content: string
}

export function StreamingBubble({ content }: StreamingBubbleProps) {
  return (
    <div className="flex gap-3 py-4">
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback className="bg-muted">
          <Brain className="h-4 w-4" />
        </AvatarFallback>
      </Avatar>
      <div className="rounded-lg px-4 py-2 max-w-[80%] bg-muted">
        <p className="whitespace-pre-wrap break-words text-sm">
          {content}
          <span className="inline-block w-2 h-4 ml-1 bg-foreground/50 animate-pulse" />
        </p>
      </div>
    </div>
  )
}
