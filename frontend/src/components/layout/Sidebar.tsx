import { useNavigate, useParams } from 'react-router-dom'
import { Plus, PanelLeft, MessagesSquare } from 'lucide-react'
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
  const { data: starredData, isLoading: starredLoading } = useSessions(1, 5, true)
  const { data: recentData, isLoading: recentLoading } = useSessions(1, 15, false)
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
      <div className="p-2 space-y-1">
        <Button
          variant="ghost"
          size="icon"
          className={collapsed ? 'mx-auto w-full' : ''}
          onClick={onToggle}
        >
          <PanelLeft className="h-4 w-4" />
        </Button>
        {collapsed ? (
          <Button
            variant="ghost"
            size="icon"
            className="mx-auto w-full"
            onClick={handleNewChat}
            disabled={createSession.isPending}
          >
            <Plus className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            variant="outline"
            className="w-full"
            onClick={handleNewChat}
            disabled={createSession.isPending}
          >
            <Plus className="h-4 w-4 mr-2" />
            New Chat
          </Button>
        )}
      </div>

      <div className="px-2">
        {collapsed ? (
          <Button
            variant="ghost"
            size="icon"
            className="mx-auto w-full text-muted-foreground hover:text-foreground"
            onClick={() => navigate('/sessions')}
          >
            <MessagesSquare className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            variant="ghost"
            className="w-full justify-start text-sm text-muted-foreground hover:text-foreground"
            onClick={() => navigate('/sessions')}
          >
            <MessagesSquare className="h-4 w-4 mr-2" />
            Sessions
          </Button>
        )}
      </div>

      <div className="mx-3 border-t border-border/50" />

      {!collapsed && (
        <>
          <ScrollArea className="flex-1 px-2">
            <SessionList
              sessions={recentData?.items || []}
              starredSessions={starredData?.items || []}
              isLoading={starredLoading || recentLoading}
              activeSessionId={sessionId}
            />
          </ScrollArea>
        </>
      )}
    </div>
  )
}
