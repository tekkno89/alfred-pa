import { useState, useEffect } from 'react'
import { Bell, BellOff, Clock, Play, Plus, Trash2, Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PomodoroTimer } from '@/components/focus/PomodoroTimer'
import {
  useFocusStatus,
  useEnableFocus,
  useDisableFocus,
  useStartPomodoro,
} from '@/hooks/useFocusMode'
import {
  type PomodoroPreset,
  DEFAULT_POMODORO_PRESETS,
  loadPomodoroPresets,
  savePomodoroCustomPresets,
} from '@/components/focus/PomodoroStartModal'

interface FocusPreset {
  id: string
  name: string
  minutes: number
}

const DEFAULT_PRESETS: FocusPreset[] = [
  { id: 'default-30', name: 'Quick focus', minutes: 30 },
  { id: 'default-60', name: 'Deep work', minutes: 60 },
  { id: 'default-120', name: 'Extended focus', minutes: 120 },
]

const STORAGE_KEY = 'focus-presets'

function loadPresets(): FocusPreset[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const custom = JSON.parse(stored) as FocusPreset[]
      return [...DEFAULT_PRESETS, ...custom]
    }
  } catch {
    // Ignore parse errors
  }
  return DEFAULT_PRESETS
}

function saveCustomPresets(presets: FocusPreset[]) {
  const custom = presets.filter(p => !p.id.startsWith('default-'))
  localStorage.setItem(STORAGE_KEY, JSON.stringify(custom))
}

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  if (mins === 0) return `${hours} hour${hours > 1 ? 's' : ''}`
  return `${hours}h ${mins}m`
}

export function FocusPage() {
  const { data: status, isLoading } = useFocusStatus()
  const enableMutation = useEnableFocus()
  const disableMutation = useDisableFocus()
  const startPomodoroMutation = useStartPomodoro()

  const [selectedDuration, setSelectedDuration] = useState<string>('60')
  const [customMinutes, setCustomMinutes] = useState<number>(45)
  const [showCustomInput, setShowCustomInput] = useState(false)
  const [presets, setPresets] = useState<FocusPreset[]>(loadPresets)
  const [showSavePreset, setShowSavePreset] = useState(false)
  const [newPresetName, setNewPresetName] = useState('')

  const [pomodoroPresets, setPomodoroPresets] = useState<PomodoroPreset[]>(loadPomodoroPresets)

  // Reload presets on mount
  useEffect(() => {
    setPresets(loadPresets())
    setPomodoroPresets(loadPomodoroPresets())
  }, [])

  const isActive = status?.is_active ?? false
  const isPomodoroActive = isActive && status?.mode === 'pomodoro'
  const isSimpleActive = isActive && status?.mode === 'simple'
  const isPending = enableMutation.isPending || disableMutation.isPending

  const handleDurationChange = (value: string) => {
    setSelectedDuration(value)
    setShowCustomInput(value === 'custom')
  }

  const handleEnable = async () => {
    let duration: number | undefined
    if (selectedDuration === 'custom') {
      duration = customMinutes
    } else if (selectedDuration === 'indefinite') {
      duration = undefined
    } else {
      duration = parseInt(selectedDuration)
    }
    await enableMutation.mutateAsync({ duration_minutes: duration })
  }

  const handleDisable = async () => {
    await disableMutation.mutateAsync()
  }

  const handleSavePreset = () => {
    if (!newPresetName.trim()) return

    const newPreset: FocusPreset = {
      id: `custom-${Date.now()}`,
      name: newPresetName.trim(),
      minutes: customMinutes,
    }

    const updated = [...presets, newPreset]
    setPresets(updated)
    saveCustomPresets(updated)
    setNewPresetName('')
    setShowSavePreset(false)
  }

  const handleDeletePreset = (id: string) => {
    const updated = presets.filter(p => p.id !== id)
    setPresets(updated)
    saveCustomPresets(updated)
  }

  const handleStartPomodoroPreset = (preset: PomodoroPreset) => {
    startPomodoroMutation.mutate({
      work_minutes: preset.workMinutes,
      break_minutes: preset.breakMinutes,
      total_sessions: preset.sessions,
    })
  }

  const handleDeletePomodoroPreset = (id: string) => {
    const updated = pomodoroPresets.filter(p => p.id !== id)
    setPomodoroPresets(updated)
    savePomodoroCustomPresets(updated)
  }

  const reloadPomodoroPresets = () => {
    setPomodoroPresets(loadPomodoroPresets())
  }

  const formatTimeRemaining = (seconds: number) => {
    const hours = Math.floor(seconds / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    if (hours > 0) {
      return `${hours}h ${mins}m remaining`
    }
    return `${mins}m remaining`
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
        <h1 className="text-3xl font-bold text-center">Focus Mode</h1>

        {/* Active session banner */}
        {isActive && !isLoading && (
          <>
            {isSimpleActive && (
              <div className="flex items-center justify-between p-4 rounded-lg bg-red-50 dark:bg-red-950">
                <div>
                  <div className="flex items-center gap-2">
                    <div className="h-3 w-3 rounded-full bg-red-500 animate-pulse" />
                    <span className="font-medium text-red-800 dark:text-red-200">
                      Focus Mode Active
                    </span>
                  </div>
                  {status?.time_remaining_seconds && (
                    <div className="text-sm text-red-600 dark:text-red-400 mt-1 flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {formatTimeRemaining(status.time_remaining_seconds)}
                    </div>
                  )}
                  {status?.custom_message && (
                    <div className="text-sm text-muted-foreground mt-2 italic">
                      "{status.custom_message}"
                    </div>
                  )}
                </div>
                <Button
                  variant="outline"
                  onClick={handleDisable}
                  disabled={isPending}
                >
                  <Bell className="h-4 w-4 mr-2" />
                  {isPending ? 'Ending...' : 'End Focus'}
                </Button>
              </div>
            )}

            {isPomodoroActive && (
              <PomodoroTimer onPresetSaved={reloadPomodoroPresets} />
            )}
          </>
        )}

        {/* Tabs */}
        <Tabs defaultValue="focus">
          <TabsList className="w-full">
            <TabsTrigger value="focus" className="flex-1" disabled={isPomodoroActive}>Focus</TabsTrigger>
            <TabsTrigger value="pomodoro" className="flex-1" disabled={isSimpleActive}>Pomodoro</TabsTrigger>
          </TabsList>

          {/* Focus Tab */}
          <TabsContent value="focus" className="space-y-6">
            {isLoading ? (
              <div className="text-center py-8 text-muted-foreground">Loading...</div>
            ) : (
              <>
                {/* Start controls */}
                <div className="space-y-4 p-4 rounded-lg border">
                  <div className="flex items-center gap-2 mb-2">
                    {isActive ? (
                      <BellOff className="h-5 w-5 text-red-500" />
                    ) : (
                      <Bell className="h-5 w-5" />
                    )}
                    <h2 className="font-semibold">Start a Focus Session</h2>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    When enabled, Alfred will auto-reply to Slack messages and minimize distractions.
                  </p>

                  <div className="flex items-center gap-4">
                    <div className="flex-1">
                      <label className="text-sm font-medium mb-2 block">Duration</label>
                      <Select value={selectedDuration} onValueChange={handleDurationChange}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="30">30 minutes</SelectItem>
                          <SelectItem value="60">1 hour</SelectItem>
                          <SelectItem value="120">2 hours</SelectItem>
                          <SelectItem value="240">4 hours</SelectItem>
                          <SelectItem value="custom">Custom duration...</SelectItem>
                          <SelectItem value="indefinite">Until I turn it off</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="pt-6">
                      <Button
                        size="lg"
                        onClick={handleEnable}
                        disabled={isActive || isPending || isPomodoroActive}
                      >
                        <BellOff className="h-4 w-4 mr-2" />
                        {isPending ? 'Starting...' : 'Start'}
                      </Button>
                    </div>
                  </div>

                  {/* Custom duration input */}
                  {showCustomInput && (
                    <div className="p-4 rounded-lg border bg-muted/30 space-y-3">
                      <div className="flex items-center gap-3">
                        <div className="flex-1">
                          <label className="text-sm font-medium mb-1 block">Minutes</label>
                          <Input
                            type="number"
                            min={1}
                            max={480}
                            value={customMinutes}
                            onChange={(e) => setCustomMinutes(parseInt(e.target.value) || 45)}
                          />
                        </div>
                        <div className="pt-6">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setShowSavePreset(!showSavePreset)}
                          >
                            <Plus className="h-4 w-4 mr-1" />
                            Save as preset
                          </Button>
                        </div>
                      </div>

                      {showSavePreset && (
                        <div className="flex gap-2">
                          <Input
                            placeholder="Preset name (e.g., Morning focus)"
                            value={newPresetName}
                            onChange={(e) => setNewPresetName(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleSavePreset()}
                          />
                          <Button size="sm" onClick={handleSavePreset} disabled={!newPresetName.trim()}>
                            <Save className="h-4 w-4" />
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Quick action presets */}
                <div className="space-y-2">
                  <h3 className="text-sm font-medium text-muted-foreground">Quick Start</h3>
                  {presets.map((preset) => (
                    <div key={preset.id} className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        className="flex-1 justify-start"
                        onClick={() => enableMutation.mutate({ duration_minutes: preset.minutes })}
                        disabled={isActive || isPending || isPomodoroActive}
                      >
                        <Clock className="h-4 w-4 mr-2" />
                        {preset.name} ({formatDuration(preset.minutes)})
                      </Button>
                      {!preset.id.startsWith('default-') && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeletePreset(preset.id)}
                        >
                          <Trash2 className="h-4 w-4 text-muted-foreground" />
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </TabsContent>

          {/* Pomodoro Tab */}
          <TabsContent value="pomodoro" className="space-y-6">
            {!isPomodoroActive && (
              <PomodoroTimer onPresetSaved={reloadPomodoroPresets} />
            )}

            <div className="space-y-2">
              <h3 className="text-sm font-medium text-muted-foreground">Quick Start</h3>
              {pomodoroPresets.map((preset) => (
                <div key={preset.id} className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    className="flex-1 justify-start"
                    onClick={() => handleStartPomodoroPreset(preset)}
                    disabled={isActive || startPomodoroMutation.isPending}
                  >
                    <Play className="h-4 w-4 mr-2" />
                    {preset.name} ({preset.workMinutes}m / {preset.breakMinutes}m x {preset.sessions})
                  </Button>
                  {!DEFAULT_POMODORO_PRESETS.some(d => d.id === preset.id) && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDeletePomodoroPreset(preset.id)}
                    >
                      <Trash2 className="h-4 w-4 text-muted-foreground" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
