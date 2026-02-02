import { SessionItem } from './SessionItem'
import type { Session } from '@/types'

interface SessionListProps {
  sessions: Session[]
  isLoading: boolean
  activeSessionId?: string
}

export function SessionList({ sessions, isLoading, activeSessionId }: SessionListProps) {
  if (isLoading) {
    return (
      <div className="space-y-2 py-2">
        {[...Array(5)].map((_, i) => (
          <div
            key={i}
            className="h-12 rounded-md bg-muted animate-pulse"
          />
        ))}
      </div>
    )
  }

  if (sessions.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        No conversations yet
      </div>
    )
  }

  return (
    <div className="space-y-1 py-2">
      {sessions.map((session) => (
        <SessionItem
          key={session.id}
          session={session}
          isActive={session.id === activeSessionId}
        />
      ))}
    </div>
  )
}
