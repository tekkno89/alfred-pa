import { useState, useEffect } from 'react'
import { Play, Plus, Trash2, Save } from 'lucide-react'
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
  isLoading?: boolean
}

const DEFAULT_PRESETS: PomodoroPreset[] = [
  { id: 'classic', name: 'Classic', workMinutes: 25, breakMinutes: 5, sessions: 4 },
  { id: 'short', name: 'Short Sprint', workMinutes: 15, breakMinutes: 3, sessions: 4 },
  { id: 'long', name: 'Deep Work', workMinutes: 50, breakMinutes: 10, sessions: 2 },
]

const STORAGE_KEY = 'pomodoro-presets'

function loadPresets(): PomodoroPreset[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const custom = JSON.parse(stored) as PomodoroPreset[]
      return [...DEFAULT_PRESETS, ...custom]
    }
  } catch {
    // Ignore parse errors
  }
  return DEFAULT_PRESETS
}

function saveCustomPresets(presets: PomodoroPreset[]) {
  const custom = presets.filter(p => !DEFAULT_PRESETS.some(d => d.id === p.id))
  localStorage.setItem(STORAGE_KEY, JSON.stringify(custom))
}

export function PomodoroStartModal({
  open,
  onOpenChange,
  onStart,
  isLoading = false,
}: PomodoroStartModalProps) {
  const [presets, setPresets] = useState<PomodoroPreset[]>(loadPresets)
  const [selectedPreset, setSelectedPreset] = useState<string | null>('classic')
  const [showCustomForm, setShowCustomForm] = useState(false)
  const [customName, setCustomName] = useState('')
  const [workMinutes, setWorkMinutes] = useState(25)
  const [breakMinutes, setBreakMinutes] = useState(5)
  const [sessions, setSessions] = useState(4)

  // Reload presets when modal opens
  useEffect(() => {
    if (open) {
      setPresets(loadPresets())
    }
  }, [open])

  // Update form values when preset is selected
  useEffect(() => {
    if (selectedPreset) {
      const preset = presets.find(p => p.id === selectedPreset)
      if (preset) {
        setWorkMinutes(preset.workMinutes)
        setBreakMinutes(preset.breakMinutes)
        setSessions(preset.sessions)
      }
    }
  }, [selectedPreset, presets])

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

    const updated = [...presets, newPreset]
    setPresets(updated)
    saveCustomPresets(updated)
    setSelectedPreset(newPreset.id)
    setShowCustomForm(false)
    setCustomName('')
  }

  const handleDeletePreset = (id: string) => {
    const updated = presets.filter(p => p.id !== id)
    setPresets(updated)
    saveCustomPresets(updated)
    if (selectedPreset === id) {
      setSelectedPreset('classic')
    }
  }

  const isDefaultPreset = (id: string) => DEFAULT_PRESETS.some(p => p.id === id)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="text-xl">🍅</span>
            Start Pomodoro
          </DialogTitle>
          <DialogDescription>
            Choose a preset or customize your session.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Preset Selection */}
          <div className="space-y-2">
            <Label>Presets</Label>
            <div className="grid grid-cols-1 gap-2">
              {presets.map((preset) => (
                <div
                  key={preset.id}
                  className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-colors ${
                    selectedPreset === preset.id
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-primary/50'
                  }`}
                  onClick={() => {
                    setSelectedPreset(preset.id)
                    setShowCustomForm(false)
                  }}
                >
                  <div>
                    <div className="font-medium">{preset.name}</div>
                    <div className="text-sm text-muted-foreground">
                      {preset.workMinutes}m work · {preset.breakMinutes}m break · {preset.sessions} sessions
                    </div>
                  </div>
                  {!isDefaultPreset(preset.id) && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDeletePreset(preset.id)
                      }}
                    >
                      <Trash2 className="h-4 w-4 text-muted-foreground" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Custom Configuration */}
          <div className="space-y-3">
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => {
                setShowCustomForm(!showCustomForm)
                setSelectedPreset(null)
              }}
            >
              <Plus className="h-4 w-4 mr-2" />
              {showCustomForm ? 'Hide Custom Options' : 'Create Custom Session'}
            </Button>

            {(showCustomForm || selectedPreset === null) && (
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

                {showCustomForm && (
                  <div className="flex gap-2">
                    <Input
                      placeholder="Preset name..."
                      value={customName}
                      onChange={(e) => setCustomName(e.target.value)}
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
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleStart} disabled={isLoading}>
            <Play className="h-4 w-4 mr-2" />
            {isLoading ? 'Starting...' : 'Start Pomodoro'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
