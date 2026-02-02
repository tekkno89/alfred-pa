import { useParams, Navigate } from 'react-router-dom'
import { useSession } from '@/hooks/useSessions'
import { ChatContainer } from '@/components/chat/ChatContainer'

export function ChatPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const { data: session, isLoading, error } = useSession(sessionId)

  if (!sessionId) {
    return <Navigate to="/" replace />
  }

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="h-8 w-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (error || !session) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <p className="text-lg font-medium text-destructive">Session not found</p>
          <p className="text-sm text-muted-foreground">
            This conversation may have been deleted
          </p>
        </div>
      </div>
    )
  }

  return <ChatContainer sessionId={sessionId} messages={session.messages} />
}
