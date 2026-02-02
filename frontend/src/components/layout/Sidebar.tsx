import { useNavigate, useParams } from 'react-router-dom'
import { Plus, ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { SessionList } from '@/components/sessions/SessionList'
import { useSessions, useCreateSession } from '@/hooks/useSessions'

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const navigate = useNavigate()
  const { sessionId } = useParams()
  const { data: sessions, isLoading } = useSessions()
  const createSession = useCreateSession()

  const handleNewChat = async () => {
    const title = new Date().toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
    const session = await createSession.mutateAsync({ title })
    navigate(`/chat/${session.id}`)
  }

  return (
    <div
      className={`border-r bg-muted/40 flex flex-col transition-all duration-200 ${
        collapsed ? 'w-14' : 'w-64'
      }`}
    >
      <div className="p-2 flex items-center justify-between">
        {!collapsed && (
          <Button
            variant="outline"
            className="flex-1 mr-2"
            onClick={handleNewChat}
            disabled={createSession.isPending}
          >
            <Plus className="h-4 w-4 mr-2" />
            New Chat
          </Button>
        )}
        {collapsed && (
          <Button
            variant="ghost"
            size="icon"
            className="mx-auto"
            onClick={handleNewChat}
            disabled={createSession.isPending}
          >
            <Plus className="h-4 w-4" />
          </Button>
        )}
        <Button variant="ghost" size="icon" onClick={onToggle}>
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </Button>
      </div>

      {!collapsed && (
        <ScrollArea className="flex-1 px-2">
          <SessionList
            sessions={sessions?.items || []}
            isLoading={isLoading}
            activeSessionId={sessionId}
          />
        </ScrollArea>
      )}
    </div>
  )
}
