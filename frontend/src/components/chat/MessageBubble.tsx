import { cn } from '@/lib/utils'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Brain, User } from 'lucide-react'
import type { Message } from '@/types'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

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
            : 'bg-muted',
          'prose prose-sm dark:prose-invert max-w-none',
          'prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1',
          'prose-pre:bg-slate-800 prose-pre:text-slate-100 prose-pre:border prose-pre:border-slate-700 prose-pre:overflow-x-auto',
          'prose-code:bg-slate-800 prose-code:text-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs',
          isUser && 'prose-invert'
        )}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {message.content}
        </ReactMarkdown>
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
      <div
        className={cn(
          'rounded-lg px-4 py-2 max-w-[80%] bg-muted',
          'prose prose-sm dark:prose-invert max-w-none',
          'prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1',
          'prose-pre:bg-slate-800 prose-pre:text-slate-100 prose-pre:border prose-pre:border-slate-700 prose-pre:overflow-x-auto',
          'prose-code:bg-slate-800 prose-code:text-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs'
        )}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content}
        </ReactMarkdown>
        <span className="inline-block w-2 h-4 ml-1 bg-foreground/50 animate-pulse" />
      </div>
    </div>
  )
}
