import { useEffect, useState, useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Play, Pause, SkipForward, Coffee } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { PomodoroStartModal } from './PomodoroStartModal'
import {
  useFocusStatus,
  useStartPomodoro,
  useSkipPomodoroPhase,
  useDisableFocus,
} from '@/hooks/useFocusMode'
import { useNotifications } from '@/hooks/useNotifications'
import type { NotificationEvent } from '@/types'

export function PomodoroTimer() {
  const queryClient = useQueryClient()
  const { data: status, isLoading } = useFocusStatus()
  const startMutation = useStartPomodoro()
  const skipMutation = useSkipPomodoroPhase()
  const disableMutation = useDisableFocus()
  const [showStartModal, setShowStartModal] = useState(false)

  // Local display time - calculated from ends_at, updated every second
  const [displayTime, setDisplayTime] = useState<number>(0)

  // Track if timer has been running (to distinguish initial 0 from countdown-to-0)
  const hasTimerStarted = useRef(false)

  // Listen for pomodoro phase change notifications and refresh status
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

  const isActive = status?.is_active && status?.mode === 'pomodoro'
  const phase = status?.pomodoro_phase
  const sessionCount = status?.pomodoro_session_count ?? 0
  const totalSessions = status?.pomodoro_total_sessions

  // Calculate and update display time from ends_at
  // This is purely for display - ARQ jobs handle actual transitions
  const endsAt = status?.ends_at

  useEffect(() => {
    if (!isActive || !endsAt) {
      setDisplayTime(0)
      hasTimerStarted.current = false
      return
    }

    const calculateRemaining = () => {
      try {
        const endsAtMs = new Date(endsAt).getTime()
        const now = Date.now()
        return Math.max(0, Math.floor((endsAtMs - now) / 1000))
      } catch {
        return 0
      }
    }

    // Set initial value
    const initialTime = calculateRemaining()
    setDisplayTime(initialTime)

    // Mark timer as started if we have time remaining
    if (initialTime > 0) {
      hasTimerStarted.current = true
    }

    // Update every second
    const interval = setInterval(() => {
      setDisplayTime(calculateRemaining())
    }, 1000)

    return () => clearInterval(interval)
  }, [isActive, endsAt])

  // Poll for phase transition when timer hits zero
  // Only poll if timer was running and reached zero (not on initial load)
  useEffect(() => {
    // Don't poll if not active, or if timer has time left, or if timer never started
    if (!isActive || displayTime !== 0 || !hasTimerStarted.current) return

    // Timer counted down to zero - poll every second until phase changes
    const pollInterval = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ['focus-status'] })
    }, 1000)

    // Also fetch immediately
    queryClient.invalidateQueries({ queryKey: ['focus-status'] })

    return () => clearInterval(pollInterval)
  }, [isActive, displayTime, queryClient])

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  const handleStart = async (config: { workMinutes: number; breakMinutes: number; sessions: number }) => {
    await startMutation.mutateAsync({
      work_minutes: config.workMinutes,
      break_minutes: config.breakMinutes,
      total_sessions: config.sessions,
    })
    setShowStartModal(false)
  }

  const handleSkip = async () => {
    await skipMutation.mutateAsync()
  }

  const handleStop = async () => {
    await disableMutation.mutateAsync()
  }

  if (isLoading) {
    return (
      <Card>
        <CardContent className="pt-6">
          <div className="text-center text-muted-foreground">Loading...</div>
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className="text-xl">🍅</span>
            Pomodoro Timer
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isActive ? (
            <div className="space-y-4">
              {/* Phase indicator */}
              <div className="text-center">
                <span
                  className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium ${
                    phase === 'work'
                      ? 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                      : 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
                  }`}
                >
                  {phase === 'work' ? (
                    <>🍅 Focus Time</>
                  ) : (
                    <><Coffee className="h-4 w-4" /> Break Time</>
                  )}
                </span>
              </div>

              {/* Timer display */}
              <div className="text-center">
                <div className="text-6xl font-mono font-bold">
                  {formatTime(displayTime)}
                </div>
                <div className="text-sm text-muted-foreground mt-2">
                  Session {sessionCount}{totalSessions ? ` of ${totalSessions}` : ''}
                </div>
              </div>

              {/* Controls */}
              <div className="flex justify-center gap-2">
                <Button variant="outline" onClick={handleSkip} disabled={skipMutation.isPending}>
                  <SkipForward className="h-4 w-4 mr-2" />
                  Skip to {phase === 'work' ? 'Break' : 'Work'}
                </Button>
                <Button variant="destructive" onClick={handleStop} disabled={disableMutation.isPending}>
                  <Pause className="h-4 w-4 mr-2" />
                  Stop
                </Button>
              </div>
            </div>
          ) : (
            <div className="text-center space-y-4">
              <p className="text-muted-foreground">
                The Pomodoro Technique helps you focus with timed work sessions and breaks.
              </p>
              <Button onClick={() => setShowStartModal(true)}>
                <Play className="h-4 w-4 mr-2" />
                Start Pomodoro
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <PomodoroStartModal
        open={showStartModal}
        onOpenChange={setShowStartModal}
        onStart={handleStart}
        isLoading={startMutation.isPending}
      />
    </>
  )
}
