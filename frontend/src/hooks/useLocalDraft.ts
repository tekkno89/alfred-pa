import { useState, useEffect, useRef, useCallback } from 'react'

export interface DraftData {
  title: string
  body: string
  tags: string[]
  isFavorited: boolean
  savedAt: number
}

function storageKey(noteId: string | undefined): string {
  return noteId ? `note-draft-${noteId}` : 'note-draft-new'
}

/** Remove a draft from localStorage by noteId. Usable outside of the hook. */
export function clearDraftForNote(noteId: string): void {
  try {
    localStorage.removeItem(`note-draft-${noteId}`)
  } catch {
    // localStorage unavailable — nothing to clean up
  }
}

function readDraft(key: string): DraftData | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    return JSON.parse(raw) as DraftData
  } catch {
    return null
  }
}

function writeDraft(key: string, data: DraftData): void {
  try {
    localStorage.setItem(key, JSON.stringify(data))
  } catch {
    // quota exceeded or unavailable — silently fail
  }
}

export function useLocalDraft(
  noteId: string | undefined,
  serverUpdatedAt: string | undefined,
  serverData?: { title: string; body: string; tags: string[]; isFavorited: boolean } | null
) {
  const key = storageKey(noteId)
  const keyRef = useRef(key)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const suppressNextWrite = useRef(false)

  const [recoveredDraft, setRecoveredDraft] = useState<DraftData | null>(null)
  const hasStaleDraft = recoveredDraft !== null

  // On mount or noteId change, check for a stale local draft
  useEffect(() => {
    keyRef.current = key

    // Reset recovery state when noteId changes
    setRecoveredDraft(null)
    suppressNextWrite.current = false

    const draft = readDraft(key)
    if (!draft) return

    if (!serverUpdatedAt) {
      if (!noteId) {
        // New note — any draft is recoverable
        setRecoveredDraft(draft)
      }
      // For existing notes still loading, wait for serverUpdatedAt
      return
    }

    const serverMs = new Date(
      serverUpdatedAt.endsWith('Z') || serverUpdatedAt.includes('+')
        ? serverUpdatedAt
        : serverUpdatedAt + 'Z'
    ).getTime()

    if (draft.savedAt > serverMs) {
      // Only show recovery if the draft actually differs from the server content
      if (serverData &&
        draft.title === serverData.title &&
        draft.body === serverData.body &&
        draft.isFavorited === serverData.isFavorited &&
        JSON.stringify(draft.tags) === JSON.stringify(serverData.tags)) {
        // Content is identical — silently discard the stale draft
        try { localStorage.removeItem(key) } catch { /* ignore */ }
      } else {
        setRecoveredDraft(draft)
      }
    } else {
      // Server is newer — discard stale draft
      try { localStorage.removeItem(key) } catch { /* ignore */ }
    }
  }, [key, serverUpdatedAt])

  const saveDraft = useCallback((data: Omit<DraftData, 'savedAt'>) => {
    if (suppressNextWrite.current) {
      suppressNextWrite.current = false
      return
    }
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => {
      if (suppressNextWrite.current) {
        suppressNextWrite.current = false
        return
      }
      writeDraft(keyRef.current, { ...data, savedAt: Date.now() })
    }, 300)
  }, [])

  const saveDraftNow = useCallback((data: Omit<DraftData, 'savedAt'>) => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    writeDraft(keyRef.current, { ...data, savedAt: Date.now() })
  }, [])

  const clearDraft = useCallback(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    suppressNextWrite.current = true
    try { localStorage.removeItem(keyRef.current) } catch { /* ignore */ }
    setRecoveredDraft(null)
  }, [])

  const dismissRecovery = useCallback(() => {
    try { localStorage.removeItem(keyRef.current) } catch { /* ignore */ }
    setRecoveredDraft(null)
  }, [])

  const acceptRecovery = useCallback((): DraftData | null => {
    const draft = recoveredDraft
    setRecoveredDraft(null)
    return draft
  }, [recoveredDraft])

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
    }
  }, [])

  return {
    saveDraft,
    saveDraftNow,
    clearDraft,
    hasStaleDraft,
    recoveredDraft,
    dismissRecovery,
    acceptRecovery,
  }
}
