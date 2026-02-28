import { useEffect, useRef } from 'react'

interface Options {
  hasUnsavedChanges: boolean
  onFlushSave: () => void
}

export function useSaveOnFocusLoss({ hasUnsavedChanges, onFlushSave }: Options) {
  const unsavedRef = useRef(hasUnsavedChanges)
  unsavedRef.current = hasUnsavedChanges

  const flushRef = useRef(onFlushSave)
  flushRef.current = onFlushSave

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden' && unsavedRef.current) {
        flushRef.current()
      }
    }

    const handleBlur = () => {
      if (unsavedRef.current) {
        flushRef.current()
      }
    }

    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (unsavedRef.current) {
        flushRef.current()
        e.preventDefault()
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('blur', handleBlur)
    window.addEventListener('beforeunload', handleBeforeUnload)

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('blur', handleBlur)
      window.removeEventListener('beforeunload', handleBeforeUnload)
    }
  }, [])
}
