import { useState } from 'react'
import { Play, Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

export interface PomodoroPreset {
  id: string
  name: string
  workMinutes: number
  breakMinutes: number
  sessions: number
}

interface PomodoroStartModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onStart: (config: { workMinutes: number; breakMinutes: number; sessions: number }) => void
  onPresetSaved?: () => void
  isLoading?: boolean
}

export const DEFAULT_POMODORO_PRESETS: PomodoroPreset[] = [
  { id: 'classic', name: 'Classic', workMinutes: 25, breakMinutes: 5, sessions: 4 },
  { id: 'short', name: 'Short Sprint', workMinutes: 15, breakMinutes: 3, sessions: 4 },
  { id: 'long', name: 'Deep Work', workMinutes: 50, breakMinutes: 10, sessions: 2 },
]

const STORAGE_KEY = 'pomodoro-presets'

export function loadPomodoroPresets(): PomodoroPreset[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const custom = JSON.parse(stored) as PomodoroPreset[]
      return [...DEFAULT_POMODORO_PRESETS, ...custom]
    }
  } catch {
    // Ignore parse errors
  }
  return DEFAULT_POMODORO_PRESETS
}

export function savePomodoroCustomPresets(presets: PomodoroPreset[]) {
  const custom = presets.filter(p => !DEFAULT_POMODORO_PRESETS.some(d => d.id === p.id))
  localStorage.setItem(STORAGE_KEY, JSON.stringify(custom))
}

export function PomodoroStartModal({
  open,
  onOpenChange,
  onStart,
  onPresetSaved,
  isLoading = false,
}: PomodoroStartModalProps) {
  const [showSavePreset, setShowSavePreset] = useState(false)
  const [customName, setCustomName] = useState('')
  const [workMinutes, setWorkMinutes] = useState(25)
  const [breakMinutes, setBreakMinutes] = useState(5)
  const [sessions, setSessions] = useState(4)

  const handleStart = () => {
    onStart({ workMinutes, breakMinutes, sessions })
  }

  const handleSavePreset = () => {
    if (!customName.trim()) return

    const newPreset: PomodoroPreset = {
      id: `custom-${Date.now()}`,
      name: customName.trim(),
      workMinutes,
      breakMinutes,
      sessions,
    }

    const existing = loadPomodoroPresets()
    const updated = [...existing, newPreset]
    savePomodoroCustomPresets(updated)
    setCustomName('')
    setShowSavePreset(false)
    onPresetSaved?.()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="text-xl">🍅</span>
            Custom Pomodoro Session
          </DialogTitle>
          <DialogDescription>
            Configure a custom work/break session or save it as a preset.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-3 p-3 rounded-lg border bg-muted/30">
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1">
                <Label htmlFor="work" className="text-xs">Work (min)</Label>
                <Input
                  id="work"
                  type="number"
                  min={1}
                  max={120}
                  value={workMinutes}
                  onChange={(e) => setWorkMinutes(parseInt(e.target.value) || 25)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="break" className="text-xs">Break (min)</Label>
                <Input
                  id="break"
                  type="number"
                  min={1}
                  max={60}
                  value={breakMinutes}
                  onChange={(e) => setBreakMinutes(parseInt(e.target.value) || 5)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="sessions" className="text-xs">Sessions</Label>
                <Input
                  id="sessions"
                  type="number"
                  min={1}
                  max={12}
                  value={sessions}
                  onChange={(e) => setSessions(parseInt(e.target.value) || 4)}
                />
              </div>
            </div>

            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => setShowSavePreset(!showSavePreset)}
            >
              <Save className="h-4 w-4 mr-2" />
              Save as Preset
            </Button>

            {showSavePreset && (
              <div className="flex gap-2">
                <Input
                  placeholder="Preset name..."
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSavePreset()}
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSavePreset}
                  disabled={!customName.trim()}
                >
                  <Save className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleStart} disabled={isLoading}>
            <Play className="h-4 w-4 mr-2" />
            {isLoading ? 'Starting...' : 'Start Session'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
