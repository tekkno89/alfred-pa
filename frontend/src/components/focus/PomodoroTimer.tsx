import { useEffect, useState } from 'react'
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

export function PomodoroTimer() {
  const { data: status, isLoading } = useFocusStatus()
  const startMutation = useStartPomodoro()
  const skipMutation = useSkipPomodoroPhase()
  const disableMutation = useDisableFocus()
  const [timeRemaining, setTimeRemaining] = useState<number>(0)
  const [showStartModal, setShowStartModal] = useState(false)

  const isActive = status?.is_active && status?.mode === 'pomodoro'
  const phase = status?.pomodoro_phase
  const sessionCount = status?.pomodoro_session_count ?? 0
  const totalSessions = status?.pomodoro_total_sessions

  // Update countdown timer
  useEffect(() => {
    if (status?.time_remaining_seconds) {
      setTimeRemaining(status.time_remaining_seconds)
    }
  }, [status?.time_remaining_seconds])

  useEffect(() => {
    if (!isActive || timeRemaining <= 0) return

    const interval = setInterval(() => {
      setTimeRemaining((prev) => Math.max(0, prev - 1))
    }, 1000)

    return () => clearInterval(interval)
  }, [isActive, timeRemaining])

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
                  {formatTime(timeRemaining)}
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
