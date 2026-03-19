import { useEffect, useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Bell, BellOff, Coffee, Play, Square } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useFocusStatus, useEnableFocus, useDisableFocus, useStartPomodoro } from '@/hooks/useFocusMode'
import { useNotifications } from '@/hooks/useNotifications'
import { loadPomodoroPresets, type PomodoroPreset } from '@/components/focus/PomodoroStartModal'
import type { NotificationEvent } from '@/types'

interface FocusPreset {
  id: string
  name: string
  minutes: number
}

const DEFAULT_FOCUS_PRESETS: FocusPreset[] = [
  { id: 'default-30', name: 'Quick focus', minutes: 30 },
  { id: 'default-60', name: 'Deep work', minutes: 60 },
  { id: 'default-120', name: 'Extended focus', minutes: 120 },
]

function loadFocusPresets(): FocusPreset[] {
  try {
    const stored = localStorage.getItem('focus-presets')
    if (stored) {
      const custom = JSON.parse(stored) as FocusPreset[]
      return [...DEFAULT_FOCUS_PRESETS, ...custom]
    }
  } catch {
    // ignore
  }
  return DEFAULT_FOCUS_PRESETS
}

export function FocusCard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: status, isLoading } = useFocusStatus()
  const enableMutation = useEnableFocus()
  const disableMutation = useDisableFocus()
  const startPomodoroMutation = useStartPomodoro()
  const [displayTime, setDisplayTime] = useState(0)
  const hasTimerStarted = useRef(false)

  // Listen for focus/pomodoro phase change notifications
  const handleNotification = useCallback(
    (event: NotificationEvent) => {
      if (
        event.type === 'pomodoro_work_started' ||
        event.type === 'pomodoro_break_started' ||
        event.type === 'pomodoro_complete' ||
        event.type === 'focus_ended'
      ) {
        queryClient.invalidateQueries({ queryKey: ['focus-status'] })
      }
    },
    [queryClient]
  )
  useNotifications(handleNotification)

  const [mode, setMode] = useState<'focus' | 'pomodoro'>('focus')
  const [selectedFocus, setSelectedFocus] = useState('60')
  const [selectedPomodoro, setSelectedPomodoro] = useState('classic')
  const [focusPresets] = useState<FocusPreset[]>(loadFocusPresets)
  const [pomodoroPresets] = useState<PomodoroPreset[]>(loadPomodoroPresets)

  // Custom focus modal state
  const [showCustomFocus, setShowCustomFocus] = useState(false)
  const [customMinutes, setCustomMinutes] = useState(45)

  // Custom pomodoro modal state
  const [showCustomPomodoro, setShowCustomPomodoro] = useState(false)
  const [customWork, setCustomWork] = useState(25)
  const [customBreak, setCustomBreak] = useState(5)
  const [customSessions, setCustomSessions] = useState(4)

  const isActive = status?.is_active ?? false
  const isPomodoro = isActive && status?.mode === 'pomodoro'
  const isBreak = isPomodoro && status?.pomodoro_phase === 'break'
  const endsAt = status?.ends_at

  useEffect(() => {
    if (!isActive || !endsAt) {
      setDisplayTime(0)
      hasTimerStarted.current = false
      return
    }

    const calculateRemaining = () => {
      try {
        return Math.max(0, Math.floor((new Date(endsAt).getTime() - Date.now()) / 1000))
      } catch {
        return 0
      }
    }

    const initial = calculateRemaining()
    setDisplayTime(initial)
    if (initial > 0) hasTimerStarted.current = true

    const interval = setInterval(() => {
      setDisplayTime(calculateRemaining())
    }, 1000)

    return () => clearInterval(interval)
  }, [isActive, endsAt])

  const formatTime = (seconds: number) => {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = seconds % 60
    const pad = (n: number) => n.toString().padStart(2, '0')
    return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
  }

  const isPending = enableMutation.isPending || disableMutation.isPending || startPomodoroMutation.isPending

  const handleStop = async () => {
    await disableMutation.mutateAsync()
  }

  const handleFocusChange = (value: string) => {
    if (value === 'custom') {
      setShowCustomFocus(true)
      return
    }
    setSelectedFocus(value)
  }

  const handlePomodoroChange = (value: string) => {
    if (value === 'custom') {
      setShowCustomPomodoro(true)
      return
    }
    setSelectedPomodoro(value)
  }

  const handleStartFocus = async () => {
    if (selectedFocus === 'indefinite') {
      await enableMutation.mutateAsync({ duration_minutes: undefined })
    } else {
      await enableMutation.mutateAsync({ duration_minutes: parseInt(selectedFocus) })
    }
  }

  const handleStartCustomFocus = async () => {
    await enableMutation.mutateAsync({ duration_minutes: customMinutes })
    setShowCustomFocus(false)
  }

  const handleStartPomodoro = async () => {
    const preset = pomodoroPresets.find(p => p.id === selectedPomodoro)
    if (preset) {
      await startPomodoroMutation.mutateAsync({
        work_minutes: preset.workMinutes,
        break_minutes: preset.breakMinutes,
        total_sessions: preset.sessions,
      })
    }
  }

  const handleStartCustomPomodoro = async () => {
    await startPomodoroMutation.mutateAsync({
      work_minutes: customWork,
      break_minutes: customBreak,
      total_sessions: customSessions,
    })
    setShowCustomPomodoro(false)
  }

  return (
    <>
      <Card className="hover:shadow-md transition-shadow h-full flex flex-col">
        <CardHeader className="pb-2">
          <CardTitle
            className="flex items-center gap-2 text-base cursor-pointer"
            onClick={() => navigate('/focus')}
          >
            <Bell className="h-4 w-4" />
            Focus Mode
          </CardTitle>
        </CardHeader>
        <CardContent className="flex-1">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : !isActive ? (
            <div className="w-full space-y-3">
              {/* Focus / Pomodoro toggle */}
              <div className="flex rounded-lg bg-muted p-0.5">
                <button
                  className={`flex-1 text-xs font-medium py-1.5 rounded-md transition-colors ${
                    mode === 'focus'
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                  onClick={() => setMode('focus')}
                >
                  <BellOff className="h-3 w-3 inline mr-1" />
                  Focus
                </button>
                <button
                  className={`flex-1 text-xs font-medium py-1.5 rounded-md transition-colors ${
                    mode === 'pomodoro'
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                  onClick={() => setMode('pomodoro')}
                >
                  🍅 Pomodoro
                </button>
              </div>

              {mode === 'focus' ? (
                <div className="space-y-2">
                  <Select value={selectedFocus} onValueChange={handleFocusChange}>
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="30">30 minutes</SelectItem>
                      <SelectItem value="60">1 hour</SelectItem>
                      <SelectItem value="120">2 hours</SelectItem>
                      <SelectItem value="240">4 hours</SelectItem>
                      <SelectItem value="indefinite">Until I turn it off</SelectItem>
                      {focusPresets
                        .filter(p => !p.id.startsWith('default-'))
                        .map(p => (
                          <SelectItem key={p.id} value={String(p.minutes)}>
                            {p.name} ({p.minutes}m)
                          </SelectItem>
                        ))}
                      <SelectItem value="custom">Custom duration...</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button
                    size="sm"
                    className="w-full"
                    disabled={isPending}
                    onClick={handleStartFocus}
                  >
                    <BellOff className="h-3.5 w-3.5 mr-1.5" />
                    {isPending ? 'Starting...' : 'Start Focus'}
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  <Select value={selectedPomodoro} onValueChange={handlePomodoroChange}>
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {pomodoroPresets.map(p => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.name} ({p.workMinutes}m/{p.breakMinutes}m x{p.sessions})
                        </SelectItem>
                      ))}
                      <SelectItem value="custom">Custom session...</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button
                    size="sm"
                    className="w-full"
                    disabled={isPending}
                    onClick={handleStartPomodoro}
                  >
                    <Play className="h-3.5 w-3.5 mr-1.5" />
                    {isPending ? 'Starting...' : 'Start Pomodoro'}
                  </Button>
                </div>
              )}
            </div>
          ) : isPomodoro ? (
            <div className="w-full space-y-3">
              <div
                className="text-center space-y-3 cursor-pointer"
                onClick={() => navigate('/focus')}
              >
                <span
                  className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    isBreak
                      ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
                      : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                  }`}
                >
                  {isBreak ? (
                    <><Coffee className="h-3 w-3" /> Break</>
                  ) : (
                    <><span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" /> Focus</>
                  )}
                </span>
                <div className="text-4xl font-mono font-bold">{formatTime(displayTime)}</div>
                <p className="text-xs text-muted-foreground">
                  Session {status?.pomodoro_session_count ?? 1}
                  {status?.pomodoro_total_sessions ? ` of ${status.pomodoro_total_sessions}` : ''}
                </p>
              </div>
              <Button
                variant="destructive"
                size="sm"
                className="w-full"
                disabled={disableMutation.isPending}
                onClick={handleStop}
              >
                <Square className="h-3.5 w-3.5 mr-1.5" />
                {disableMutation.isPending ? 'Stopping...' : 'Stop'}
              </Button>
            </div>
          ) : (
            <div className="w-full space-y-3">
              <div
                className="text-center space-y-3 cursor-pointer"
                onClick={() => navigate('/focus')}
              >
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
                  <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
                  Focus Mode Active
                </span>
                {endsAt ? (
                  <>
                    <div className="text-4xl font-mono font-bold">{formatTime(displayTime)}</div>
                    <p className="text-xs text-muted-foreground">remaining</p>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">Indefinite session</p>
                )}
              </div>
              <Button
                variant="destructive"
                size="sm"
                className="w-full"
                disabled={disableMutation.isPending}
                onClick={handleStop}
              >
                <Square className="h-3.5 w-3.5 mr-1.5" />
                {disableMutation.isPending ? 'Stopping...' : 'Stop'}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Custom Focus Duration Modal */}
      <Dialog open={showCustomFocus} onOpenChange={setShowCustomFocus}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Custom Focus Duration</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="custom-minutes">Duration (minutes)</Label>
            <Input
              id="custom-minutes"
              type="number"
              min={1}
              max={480}
              value={customMinutes}
              onChange={(e) => setCustomMinutes(parseInt(e.target.value) || 45)}
              className="mt-1"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCustomFocus(false)}>
              Cancel
            </Button>
            <Button onClick={handleStartCustomFocus} disabled={isPending}>
              <BellOff className="h-4 w-4 mr-2" />
              {isPending ? 'Starting...' : 'Start Focus'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Custom Pomodoro Session Modal */}
      <Dialog open={showCustomPomodoro} onOpenChange={setShowCustomPomodoro}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Custom Pomodoro Session</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-3 gap-3 py-4">
            <div className="space-y-1">
              <Label htmlFor="custom-work" className="text-xs">Work (min)</Label>
              <Input
                id="custom-work"
                type="number"
                min={1}
                max={120}
                value={customWork}
                onChange={(e) => setCustomWork(parseInt(e.target.value) || 25)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="custom-break" className="text-xs">Break (min)</Label>
              <Input
                id="custom-break"
                type="number"
                min={1}
                max={60}
                value={customBreak}
                onChange={(e) => setCustomBreak(parseInt(e.target.value) || 5)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="custom-sessions" className="text-xs">Sessions</Label>
              <Input
                id="custom-sessions"
                type="number"
                min={1}
                max={12}
                value={customSessions}
                onChange={(e) => setCustomSessions(parseInt(e.target.value) || 4)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCustomPomodoro(false)}>
              Cancel
            </Button>
            <Button onClick={handleStartCustomPomodoro} disabled={isPending}>
              <Play className="h-4 w-4 mr-2" />
              {isPending ? 'Starting...' : 'Start Pomodoro'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
