import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Star, Hash, ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useSessions, useToggleSessionStar } from '@/hooks/useSessions'
import { cn } from '@/lib/utils'

export function SessionsPage() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const size = 20
  const { data, isLoading } = useSessions(page, size)
  const toggleStar = useToggleSessionStar()

  const totalPages = data ? Math.ceil(data.total / size) : 0

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  return (
    <div className="h-full overflow-auto p-6">
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold">All Sessions</h1>
          <p className="text-muted-foreground">
            Browse all your conversations
          </p>
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-16 rounded-lg bg-muted animate-pulse" />
            ))}
          </div>
        ) : data && data.items.length > 0 ? (
          <div className="space-y-2">
            {data.items.map((session) => (
              <div
                key={session.id}
                className="flex items-center gap-3 rounded-lg border p-3 cursor-pointer hover:bg-accent transition-colors"
                onClick={() => navigate(`/chat/${session.id}`)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium truncate">
                      {session.title || 'New Chat'}
                    </span>
                    {session.source === 'slack' && (
                      <Badge variant="secondary" className="shrink-0 text-xs py-0 px-1">
                        <Hash className="h-3 w-3 mr-0.5" />
                        Slack
                      </Badge>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {formatDate(session.updated_at)}
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className={cn(
                    'h-8 w-8 shrink-0',
                    session.is_starred ? 'text-yellow-500' : 'text-muted-foreground'
                  )}
                  onClick={(e) => {
                    e.stopPropagation()
                    toggleStar.mutate(session.id)
                  }}
                >
                  <Star className={cn('h-4 w-4', session.is_starred && 'fill-current')} />
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-12 text-center text-sm text-muted-foreground">
            No sessions found
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-4 pt-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              <ChevronLeft className="h-4 w-4 mr-1" />
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              Next
              <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
