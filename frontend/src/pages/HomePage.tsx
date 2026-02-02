import { useNavigate } from 'react-router-dom'
import { Plus, Brain } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useCreateSession } from '@/hooks/useSessions'

export function HomePage() {
  const navigate = useNavigate()
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
    <div className="h-full flex items-center justify-center">
      <div className="text-center space-y-6">
        <div className="flex justify-center">
          <div className="h-20 w-20 rounded-full bg-muted flex items-center justify-center">
            <Brain className="h-10 w-10" />
          </div>
        </div>
        <div>
          <h1 className="text-3xl font-bold mb-2">Welcome to Alfred</h1>
          <p className="text-muted-foreground max-w-md">
            Your personal AI assistant. Start a conversation or select one from the sidebar.
          </p>
        </div>
        <Button
          size="lg"
          onClick={handleNewChat}
          disabled={createSession.isPending}
        >
          <Plus className="h-5 w-5 mr-2" />
          {createSession.isPending ? 'Creating...' : 'New Conversation'}
        </Button>
      </div>
    </div>
  )
}
