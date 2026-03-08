import { useState, useRef, useEffect, useMemo, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Brain, Send, MoreVertical } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { BatmanRunner } from '@/components/game/BatmanRunner'
import { useCreateSession } from '@/hooks/useSessions'
import { useAvailableCards, useDashboardPreferences } from '@/hooks/useDashboard'
import { BartCard } from '@/components/dashboard/BartCard'
import { NotesCard } from '@/components/dashboard/NotesCard'
import { TodosCard } from '@/components/dashboard/TodosCard'
import { CalendarCard } from '@/components/dashboard/CalendarCard'
import { DashboardConfigDialog } from '@/components/dashboard/DashboardConfigDialog'
import type { BartStationPreference, DashboardPreference } from '@/types'

const CARD_RENDERERS: Record<string, (prefs: DashboardPreference | undefined) => ReactNode> = {
  bart: (pref) => {
    const stations: BartStationPreference[] =
      (pref?.preferences?.stations as BartStationPreference[]) || []
    return <BartCard stations={stations} />
  },
  todos: () => <TodosCard />,
  notes: () => <NotesCard />,
  calendar: () => <CalendarCard />,
}

export function HomePage() {
  const navigate = useNavigate()
  const createSession = useCreateSession()
  const { data: availableCards } = useAvailableCards()
  const { data: prefs } = useDashboardPreferences()
  const [input, setInput] = useState('')
  const [configOpen, setConfigOpen] = useState(false)
  const [gameEnabled, setGameEnabled] = useState(() => {
    try { return localStorage.getItem('batman-runner-enabled') === '1' } catch { return false }
  })
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const toggleGame = () => {
    setGameEnabled(prev => {
      const next = !prev
      try { localStorage.setItem('batman-runner-enabled', next ? '1' : '0') } catch {}
      return next
    })
  }

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.focus()
    }
  }, [])

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
    }
  }, [input])

  const handleSubmit = async () => {
    if (!input.trim() || createSession.isPending) return

    const title = new Date().toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
    const session = await createSession.mutateAsync({ title })
    navigate(`/chat/${session.id}`, { state: { initialMessage: input.trim() } })
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const visibleCards = useMemo(() => {
    if (!availableCards) return []

    return availableCards
      .map((cardType) => {
        const pref = prefs?.items.find((p) => p.card_type === cardType)
        const visible = pref ? pref.preferences?.visible !== false : true
        const sortOrder = pref?.sort_order ?? Infinity
        return { cardType, pref, visible, sortOrder }
      })
      .filter((c) => c.visible)
      .sort((a, b) => {
        if (a.sortOrder === Infinity && b.sortOrder === Infinity)
          return a.cardType.localeCompare(b.cardType)
        if (a.sortOrder === Infinity) return 1
        if (b.sortOrder === Infinity) return -1
        return a.sortOrder - b.sortOrder
      })
  }, [availableCards, prefs])

  const hasCards = visibleCards.length > 0
  const hasAnyAvailable = (availableCards?.length ?? 0) > 0

  return (
    <div className="h-full flex flex-col">
      {/* Dashboard area (scrollable) */}
      <div className="flex-1 overflow-y-auto p-4 relative">
        {hasCards && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 absolute top-2 right-2"
            onClick={() => setConfigOpen(true)}
          >
            <MoreVertical className="h-4 w-4" />
          </Button>
        )}
        {hasCards ? (
          <div className="max-w-5xl mx-auto">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 auto-rows-[minmax(220px,auto)]">
              {visibleCards.map(({ cardType, pref }) => {
                const render = CARD_RENDERERS[cardType]
                if (!render) return null
                return <div key={cardType} className="min-w-0">{render(pref)}</div>
              })}
            </div>
          </div>
        ) : (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-4">
              <div className="flex justify-center">
                <div className="h-20 w-20 rounded-full bg-muted flex items-center justify-center">
                  <Brain className="h-10 w-10" />
                </div>
              </div>
              <div>
                <h1 className="text-3xl font-bold mb-2">Welcome to Alfred</h1>
                <p className="text-muted-foreground max-w-md mx-auto">
                  Your personal AI assistant. Start a conversation below or select one from the sidebar.
                </p>
              </div>
              {hasAnyAvailable && (
                <Button variant="outline" size="sm" onClick={() => setConfigOpen(true)}>
                  <MoreVertical className="h-4 w-4 mr-1" />
                  Configure Dashboard
                </Button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Bottom pinned section */}
      <div className="shrink-0">
        {/* Game + bat symbol wrapper */}
        <div className="relative">
          {gameEnabled && <BatmanRunner />}
          {/* Hidden bat symbol toggle */}
          <button
            onClick={toggleGame}
            className="absolute bottom-1 right-6 transition-opacity duration-300 cursor-default z-20 group/bat"
            style={{ opacity: 0.06 }}
            onMouseEnter={e => { e.currentTarget.style.opacity = '0.5' }}
            onMouseLeave={e => { e.currentTarget.style.opacity = '0.06' }}
            title=""
            aria-label="Toggle game"
          >
            <img src="/bat-symbol.png" alt="" className="w-11 h-auto" draggable={false} />
          </button>
        </div>

        {/* Chat input */}
        <div className="border-t bg-background p-4">
        <div className="max-w-2xl mx-auto">
          <div className="flex gap-2">
            <Textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Send a message..."
              className="min-h-[44px] max-h-[200px] resize-none"
              rows={1}
              disabled={createSession.isPending}
            />
            <Button
              onClick={handleSubmit}
              disabled={!input.trim() || createSession.isPending}
              className="shrink-0"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-1 text-center">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
        </div>
      </div>

      <DashboardConfigDialog open={configOpen} onOpenChange={setConfigOpen} />
    </div>
  )
}
