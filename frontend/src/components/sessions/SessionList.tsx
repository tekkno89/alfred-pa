import { SessionItem } from './SessionItem'
import type { Session } from '@/types'

interface SessionListProps {
  sessions: Session[]
  isLoading: boolean
  activeSessionId?: string
  starredSessions?: Session[]
}

export function SessionList({ sessions, isLoading, activeSessionId, starredSessions }: SessionListProps) {
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

  const hasStarred = starredSessions && starredSessions.length > 0
  const hasRecent = sessions.length > 0

  if (!hasStarred && !hasRecent) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        No conversations yet
      </div>
    )
  }

  return (
    <div className="py-2">
      {hasStarred && (
        <>
          <div className="px-2 py-1 text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Starred
          </div>
          <div className="space-y-1">
            {starredSessions.map((session) => (
              <SessionItem
                key={session.id}
                session={session}
                isActive={session.id === activeSessionId}
              />
            ))}
          </div>
          {hasRecent && (
            <div className="px-2 py-1 mt-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Recent
            </div>
          )}
        </>
      )}
      {hasRecent && (
        <div className="space-y-1">
          {sessions.map((session) => (
            <SessionItem
              key={session.id}
              session={session}
              isActive={session.id === activeSessionId}
            />
          ))}
        </div>
      )}
    </div>
  )
}
