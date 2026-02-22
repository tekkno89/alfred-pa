import { useCallback, useRef, useEffect } from 'react'

export function useTitleFlash() {
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const originalTitleRef = useRef<string>(document.title)

  const stopTitleFlash = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    document.title = originalTitleRef.current
  }, [])

  const startTitleFlash = useCallback(
    (message: string) => {
      // Stop any existing flash
      stopTitleFlash()
      originalTitleRef.current = document.title

      let showMessage = true
      intervalRef.current = setInterval(() => {
        document.title = showMessage ? message : originalTitleRef.current
        showMessage = !showMessage
      }, 1000)
    },
    [stopTitleFlash]
  )

  // Auto-stop when tab becomes visible
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        stopTitleFlash()
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibility)
      stopTitleFlash()
    }
  }, [stopTitleFlash])

  return { startTitleFlash, stopTitleFlash }
}
