import { useState, useEffect, useRef } from 'react'
import { Train, StickyNote, CheckSquare, CalendarDays, Youtube, Bell, Inbox, GripVertical, type LucideIcon } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import { useAvailableCards, useDashboardPreferences, useUpdateDashboardPreference } from '@/hooks/useDashboard'

const CARD_META: Record<string, { label: string; icon: LucideIcon }> = {
  bart: { label: 'BART Departures', icon: Train },
  todos: { label: 'Todos', icon: CheckSquare },
  notes: { label: 'Notes', icon: StickyNote },
  calendar: { label: 'Calendar', icon: CalendarDays },
  youtube: { label: 'YouTube', icon: Youtube },
  focus: { label: 'Focus Mode', icon: Bell },
  triage: { label: 'Slack Triage', icon: Inbox },
}

interface CardConfig {
  cardType: string
  label: string
  icon: LucideIcon
  visible: boolean
  sortOrder: number
}

interface DashboardConfigDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function DashboardConfigDialog({ open, onOpenChange }: DashboardConfigDialogProps) {
  const { data: availableCards } = useAvailableCards()
  const { data: prefs } = useDashboardPreferences()
  const updatePref = useUpdateDashboardPreference()
  const [cards, setCards] = useState<CardConfig[]>([])
  const [saving, setSaving] = useState(false)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)
  const dragNodeRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!availableCards || !open) return

    const configs: CardConfig[] = availableCards.map((cardType) => {
      const meta = CARD_META[cardType] ?? { label: cardType, icon: StickyNote }
      const pref = prefs?.items.find((p) => p.card_type === cardType)
      const visible = pref ? (pref.preferences?.visible !== false) : true
      const sortOrder = pref?.sort_order ?? Infinity
      return { cardType, label: meta.label, icon: meta.icon, visible, sortOrder }
    })

    configs.sort((a, b) => {
      if (a.sortOrder === Infinity && b.sortOrder === Infinity) return a.label.localeCompare(b.label)
      if (a.sortOrder === Infinity) return 1
      if (b.sortOrder === Infinity) return -1
      return a.sortOrder - b.sortOrder
    })

    setCards(configs.map((c, i) => ({ ...c, sortOrder: i })))
  }, [availableCards, prefs, open])

  const handleDragStart = (e: React.DragEvent, index: number) => {
    setDragIndex(index)
    dragNodeRef.current = e.currentTarget as HTMLDivElement
    e.dataTransfer.effectAllowed = 'move'
    // Make the drag image slightly transparent
    requestAnimationFrame(() => {
      if (dragNodeRef.current) {
        dragNodeRef.current.style.opacity = '0.4'
      }
    })
  }

  const handleDragEnd = () => {
    if (dragNodeRef.current) {
      dragNodeRef.current.style.opacity = '1'
    }
    if (dragIndex !== null && overIndex !== null && dragIndex !== overIndex) {
      setCards((prev) => {
        const next = [...prev]
        const [moved] = next.splice(dragIndex, 1)
        next.splice(overIndex, 0, moved)
        return next.map((c, i) => ({ ...c, sortOrder: i }))
      })
    }
    setDragIndex(null)
    setOverIndex(null)
    dragNodeRef.current = null
  }

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setOverIndex(index)
  }

  const toggleVisible = (index: number) => {
    setCards((prev) =>
      prev.map((c, i) => (i === index ? { ...c, visible: !c.visible } : c))
    )
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      for (const card of cards) {
        const existingPref = prefs?.items.find((p) => p.card_type === card.cardType)
        const merged = { ...(existingPref?.preferences ?? {}), visible: card.visible }
        await updatePref.mutateAsync({
          cardType: card.cardType,
          data: { preferences: merged, sort_order: card.sortOrder },
        })
      }
      onOpenChange(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Configure Dashboard</DialogTitle>
        </DialogHeader>
        <div className="space-y-1 py-2">
          {cards.map((card, index) => {
            const Icon = card.icon
            const isOver = overIndex === index && dragIndex !== null && dragIndex !== index
            return (
              <div
                key={card.cardType}
                draggable
                onDragStart={(e) => handleDragStart(e, index)}
                onDragEnd={handleDragEnd}
                onDragOver={(e) => handleDragOver(e, index)}
                className={
                  'flex items-center gap-3 rounded-md border px-3 py-2 transition-colors' +
                  (isOver ? ' border-primary bg-accent' : '')
                }
              >
                <GripVertical className="h-4 w-4 shrink-0 text-muted-foreground cursor-grab active:cursor-grabbing" />
                <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="flex-1 text-sm font-medium select-none">{card.label}</span>
                <Switch
                  checked={card.visible}
                  onCheckedChange={() => toggleVisible(index)}
                />
              </div>
            )
          })}
          {cards.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">
              No dashboard cards available.
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
