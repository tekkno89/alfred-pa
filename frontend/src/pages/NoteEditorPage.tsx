import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Star, Eye, EyeOff, Archive, Trash2, Save, X, RefreshCw, AlertCircle, WifiOff } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useNote, useCreateNote, useUpdateNote, useArchiveNote, useDeleteNote } from '@/hooks/useNotes'
import { useLocalDraft, clearDraftForNote } from '@/hooks/useLocalDraft'
import { useSaveOnFocusLoss } from '@/hooks/useSaveOnFocusLoss'
import { useOnlineStatus } from '@/hooks/useOnlineStatus'
import { useMarkdownEditor } from '@/hooks/useMarkdownEditor'
import { ApiRequestError } from '@/lib/api'
import { cn } from '@/lib/utils'

export function NoteEditorPage() {
  const navigate = useNavigate()
  const { noteId } = useParams<{ noteId: string }>()
  const isNew = !noteId

  const { data: existingNote, isLoading } = useNote(noteId)
  const createNote = useCreateNote()
  const updateNote = useUpdateNote()
  const archiveNote = useArchiveNote()
  const deleteNote = useDeleteNote()

  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [isFavorited, setIsFavorited] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error' | 'offline' | 'retrying'>('idle')
  const [initialized, setInitialized] = useState(false)

  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isSaving = useRef(false)
  const noteIdRef = useRef(noteId)
  noteIdRef.current = noteId

  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryCount = useRef(0)
  const MAX_RETRIES = 3
  const RETRY_DELAYS = [2000, 5000, 10000]

  const isOnline = useOnlineStatus()
  const { textareaRef, onKeyDown: handleEditorKeyDown } = useMarkdownEditor(body, setBody)

  // Snapshot of last-saved state for unsaved change detection
  const lastSavedSnapshot = useRef<{ title: string; body: string; tags: string[]; isFavorited: boolean } | null>(null)

  // Local draft persistence
  const {
    saveDraft,
    saveDraftNow,
    clearDraft,
    hasStaleDraft,
    recoveredDraft,
    dismissRecovery,
    acceptRecovery,
  } = useLocalDraft(noteId, existingNote?.updated_at, existingNote ? {
    title: existingNote.title,
    body: existingNote.body,
    tags: existingNote.tags || [],
    isFavorited: existingNote.is_favorited,
  } : null)

  // Compute whether there are unsaved changes
  const hasUnsavedChanges = (() => {
    const snap = lastSavedSnapshot.current
    if (!snap) return isNew && (!!title || !!body)
    return snap.title !== title || snap.body !== body ||
      snap.isFavorited !== isFavorited ||
      JSON.stringify(snap.tags) !== JSON.stringify(tags)
  })()

  // Load existing note data
  useEffect(() => {
    if (existingNote && !initialized) {
      setTitle(existingNote.title)
      setBody(existingNote.body)
      setTags(existingNote.tags || [])
      setIsFavorited(existingNote.is_favorited)
      lastSavedSnapshot.current = {
        title: existingNote.title,
        body: existingNote.body,
        tags: existingNote.tags || [],
        isFavorited: existingNote.is_favorited,
      }
      setInitialized(true)
    }
  }, [existingNote, initialized])

  // Mark as initialized for new notes
  useEffect(() => {
    if (isNew) {
      setInitialized(true)
    }
  }, [isNew])

  // Stable save function via ref — avoids re-triggering the debounce effect
  const doSaveRef = useRef<() => void>(() => {})
  doSaveRef.current = () => {
    if (!navigator.onLine) {
      setSaveStatus('offline')
      return
    }
    const id = noteIdRef.current
    if (!id || isSaving.current) return
    // Skip if nothing changed since last save (prevents wasteful initial save on load)
    const snap = lastSavedSnapshot.current
    if (snap && snap.title === title && snap.body === body &&
      snap.isFavorited === isFavorited &&
      JSON.stringify(snap.tags) === JSON.stringify(tags)) return
    isSaving.current = true
    setSaveStatus('saving')
    const snapshot = { title, body, isFavorited, tags: [...tags] }
    updateNote.mutate(
      { id, data: { title, body, is_favorited: isFavorited, tags } },
      {
        onSuccess: () => {
          isSaving.current = false
          retryCount.current = 0
          setSaveStatus('saved')
          lastSavedSnapshot.current = snapshot
          clearDraft()
        },
        onError: (error) => {
          isSaving.current = false
          const isRetryable =
            !navigator.onLine ||
            error instanceof TypeError ||
            (error instanceof ApiRequestError && error.status >= 500)

          if (!isRetryable) {
            setSaveStatus('error')
            return
          }
          if (!navigator.onLine) {
            setSaveStatus('offline')
            return
          }
          if (retryCount.current < MAX_RETRIES) {
            const delay = RETRY_DELAYS[retryCount.current] ?? 10000
            retryCount.current++
            setSaveStatus('retrying')
            retryTimer.current = setTimeout(() => {
              if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
              doSaveRef.current()
            }, delay)
          } else {
            retryCount.current = 0
            setSaveStatus('error')
          }
        },
      }
    )
  }

  const doCreateRef = useRef<() => void>(() => {})
  doCreateRef.current = () => {
    if (!navigator.onLine) {
      setSaveStatus('offline')
      return
    }
    if (isSaving.current) return
    isSaving.current = true
    setSaveStatus('saving')
    const snapshot = { title, body, isFavorited, tags: [...tags] }
    createNote.mutate(
      { title, body, is_favorited: isFavorited, tags },
      {
        onSuccess: (note) => {
          isSaving.current = false
          retryCount.current = 0
          setSaveStatus('saved')
          lastSavedSnapshot.current = snapshot
          clearDraft()
          clearDraftForNote('new')
          navigate(`/notes/${note.id}`, { replace: true })
        },
        onError: (error) => {
          isSaving.current = false
          const isRetryable =
            !navigator.onLine ||
            error instanceof TypeError ||
            (error instanceof ApiRequestError && error.status >= 500)

          if (!isRetryable) {
            setSaveStatus('error')
            return
          }
          if (!navigator.onLine) {
            setSaveStatus('offline')
            return
          }
          if (retryCount.current < MAX_RETRIES) {
            const delay = RETRY_DELAYS[retryCount.current] ?? 10000
            retryCount.current++
            setSaveStatus('retrying')
            retryTimer.current = setTimeout(() => {
              if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
              doCreateRef.current()
            }, delay)
          } else {
            retryCount.current = 0
            setSaveStatus('error')
          }
        },
      }
    )
  }

  // Write to localStorage draft on every change (300ms debounce inside the hook)
  // Skip when state matches the last-saved snapshot (e.g. on initial load)
  useEffect(() => {
    if (!initialized) return
    const snap = lastSavedSnapshot.current
    if (snap && snap.title === title && snap.body === body &&
      snap.isFavorited === isFavorited &&
      JSON.stringify(snap.tags) === JSON.stringify(tags)) return
    // For new notes, skip if nothing has been typed yet
    if (!snap && !title && !body) return
    saveDraft({ title, body, tags, isFavorited })
  }, [title, body, isFavorited, tags, initialized, saveDraft])

  // Debounced auto-save: triggers 750ms after last change to title/body/favorite
  useEffect(() => {
    if (!initialized) return

    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    autoSaveTimer.current = setTimeout(() => {
      // New edits supersede pending retries — the fresh save includes all content
      if (retryTimer.current) {
        clearTimeout(retryTimer.current)
        retryTimer.current = null
        retryCount.current = 0
      }
      if (noteIdRef.current) {
        doSaveRef.current()
      } else if (title || body) {
        // Auto-create new note once user has typed something
        doCreateRef.current()
      }
    }, 750)

    return () => {
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    }
  }, [title, body, isFavorited, tags, initialized])

  // Flush save when coming back online after offline status
  useEffect(() => {
    if (isOnline && saveStatus === 'offline') {
      const timer = setTimeout(() => {
        if (noteIdRef.current) {
          doSaveRef.current()
        } else if (title || body) {
          doCreateRef.current()
        }
      }, 500) // small delay for network to stabilize
      return () => clearTimeout(timer)
    }
  }, [isOnline, saveStatus])

  // Cleanup retry timer on unmount
  useEffect(() => {
    return () => {
      if (retryTimer.current) clearTimeout(retryTimer.current)
    }
  }, [])

  // Cmd/Ctrl+S for immediate save
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
        if (noteIdRef.current) {
          doSaveRef.current()
        } else {
          doCreateRef.current()
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // Flush save on tab switch / alt-tab / close
  const flushSave = useCallback(() => {
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    // Only flush if there are actual unsaved changes
    const snap = lastSavedSnapshot.current
    const changed = snap
      ? (snap.title !== title || snap.body !== body ||
         snap.isFavorited !== isFavorited ||
         JSON.stringify(snap.tags) !== JSON.stringify(tags))
      : (!!title || !!body)
    if (!changed) return
    saveDraftNow({ title, body, tags, isFavorited })
    if (!isSaving.current) {
      if (noteIdRef.current) {
        doSaveRef.current()
      } else if (title || body) {
        doCreateRef.current()
      }
    }
  }, [title, body, tags, isFavorited, saveDraftNow])

  useSaveOnFocusLoss({ hasUnsavedChanges, onFlushSave: flushSave })

  const handleArchive = async () => {
    if (!noteId) return
    clearDraft()
    await archiveNote.mutateAsync(noteId)
    navigate('/notes')
  }

  const handleDelete = async () => {
    if (!noteId) return
    clearDraft()
    await deleteNote.mutateAsync(noteId)
    navigate('/notes')
  }

  const toggleFavorite = () => {
    setIsFavorited((prev) => !prev)
  }

  if (!isNew && isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      <div className="shrink-0 border-b px-4 py-2 flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => { flushSave(); navigate('/notes') }}
          className="h-8 w-8 p-0"
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>

        <span className="text-sm font-medium">
          {isNew ? 'New Note' : 'Edit Note'}
        </span>

        <div className="flex-1" />

        {/* Save status */}
        {saveStatus === 'saving' && (
          <span className="text-xs text-muted-foreground">Saving...</span>
        )}
        {saveStatus === 'saved' && (
          <span className="text-xs text-muted-foreground">Saved</span>
        )}
        {saveStatus === 'retrying' && (
          <span className="text-xs text-yellow-600 dark:text-yellow-400 flex items-center gap-1">
            <RefreshCw className="h-3 w-3 animate-spin" />
            Retrying...
          </span>
        )}
        {saveStatus === 'error' && (
          <span className="text-xs text-destructive flex items-center gap-1">
            <AlertCircle className="h-3 w-3" />
            Save failed
          </span>
        )}
        {saveStatus === 'offline' && (
          <span className="text-xs text-yellow-600 dark:text-yellow-400 flex items-center gap-1">
            <WifiOff className="h-3 w-3" />
            Offline
          </span>
        )}

        {/* Star toggle */}
        <Button
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0"
          onClick={toggleFavorite}
        >
          <Star
            className={cn(
              'h-4 w-4',
              isFavorited
                ? 'fill-yellow-400 text-yellow-400'
                : 'text-muted-foreground'
            )}
          />
        </Button>

        {/* Preview toggle */}
        <Button
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0"
          onClick={() => setShowPreview(!showPreview)}
          title={showPreview ? 'Hide preview' : 'Show preview'}
        >
          {showPreview ? (
            <EyeOff className="h-4 w-4" />
          ) : (
            <Eye className="h-4 w-4" />
          )}
        </Button>

        {/* Archive (existing notes only) */}
        {!isNew && (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0"
            onClick={handleArchive}
            title="Archive"
          >
            <Archive className="h-4 w-4" />
          </Button>
        )}

        {/* Delete (existing notes only) */}
        {!isNew && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0 text-destructive hover:text-destructive"
                title="Delete"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete note permanently?</AlertDialogTitle>
                <AlertDialogDescription>
                  This action cannot be undone. The note will be permanently deleted.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleDelete}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}

        {/* Save button */}
        <Button
          size="sm"
          variant={isNew ? 'default' : 'outline'}
          onClick={() => {
            if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
            if (noteId) { doSaveRef.current() } else { doCreateRef.current() }
          }}
          disabled={createNote.isPending || updateNote.isPending}
        >
          <Save className="h-4 w-4 mr-1" />
          Save
        </Button>
      </div>

      {/* Title */}
      <div className="shrink-0 px-4 pt-3 pb-1">
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Note title"
          className="border-0 shadow-none text-xl font-semibold px-0 focus-visible:ring-0"
        />
      </div>

      {/* Tags */}
      <div className="shrink-0 px-4 pb-2 flex items-center gap-1.5 flex-wrap">
        {tags.map((tag) => (
          <span
            key={tag}
            className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground"
          >
            {tag}
            <button
              type="button"
              onClick={() => setTags((prev) => prev.filter((t) => t !== tag))}
              className="hover:text-foreground"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <Input
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          onKeyDown={(e) => {
            if ((e.key === 'Enter' || e.key === ',') && tagInput.trim()) {
              e.preventDefault()
              const newTag = tagInput.trim().replace(/,+$/, '')
              if (newTag && !tags.includes(newTag)) {
                setTags((prev) => [...prev, newTag])
              }
              setTagInput('')
            } else if (e.key === 'Backspace' && !tagInput && tags.length) {
              setTags((prev) => prev.slice(0, -1))
            }
          }}
          placeholder={tags.length ? 'Add tag...' : 'Add tags (press Enter or comma)'}
          className="border-0 shadow-none focus-visible:ring-0 h-7 text-xs px-0 w-40 flex-shrink-0"
        />
      </div>

      {/* Body + Preview */}
      <div className="flex-1 min-h-0 flex">
        {/* Editor */}
        <div className={cn('flex-1 px-4 pb-4', showPreview && 'w-1/2')}>
          <Textarea
            ref={textareaRef}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={handleEditorKeyDown}
            placeholder="Write your note... (supports Markdown)"
            className="h-full resize-none border-0 shadow-none focus-visible:ring-0 font-mono text-sm"
          />
        </div>

        {/* Preview */}
        {showPreview && (
          <div className="w-1/2 border-l px-4 pb-4 overflow-y-auto">
            <div
              className={cn(
                'prose prose-sm dark:prose-invert max-w-none pt-2',
                'prose-p:my-1 prose-headings:my-2',
                'prose-ul:my-1 prose-ul:list-disc prose-ul:pl-6',
                'prose-ol:my-1 prose-ol:list-decimal prose-ol:pl-6',
                '[&_ol_ol]:list-[lower-alpha] [&_ol_ol_ol]:list-[lower-roman]',
                'prose-pre:bg-slate-800 prose-pre:text-slate-100 prose-pre:border prose-pre:border-slate-700 prose-pre:overflow-x-auto',
                'prose-code:bg-slate-800 prose-code:text-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs'
              )}
            >
              {body ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
              ) : (
                <p className="text-muted-foreground italic">Nothing to preview</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Draft recovery dialog */}
      <Dialog open={hasStaleDraft} onOpenChange={(open) => { if (!open) dismissRecovery() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {isNew ? 'Restore unsaved draft?' : 'Recover local draft?'}
            </DialogTitle>
            <DialogDescription>
              {isNew
                ? 'An unsaved draft was found from a previous session.'
                : 'A local draft was found that is newer than the server version.'}
            </DialogDescription>
          </DialogHeader>

          {recoveredDraft && (
            <div className="grid gap-3 max-h-60 overflow-y-auto">
              {!isNew && (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Server version</p>
                  <div className="rounded border p-2 text-sm bg-muted/30">
                    <p className="font-medium">{existingNote?.title || 'Untitled'}</p>
                    <p className="text-muted-foreground text-xs line-clamp-3 mt-1">
                      {existingNote?.body || '(empty)'}
                    </p>
                  </div>
                </div>
              )}
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">Local draft</p>
                <div className="rounded border p-2 text-sm bg-muted/30">
                  <p className="font-medium">{recoveredDraft.title || 'Untitled'}</p>
                  <p className="text-muted-foreground text-xs line-clamp-3 mt-1">
                    {recoveredDraft.body || '(empty)'}
                  </p>
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={dismissRecovery}>
              {isNew ? 'Discard' : 'Use Server Version'}
            </Button>
            <Button onClick={() => {
              const draft = acceptRecovery()
              if (draft) {
                setTitle(draft.title)
                setBody(draft.body)
                setTags(draft.tags)
                setIsFavorited(draft.isFavorited)
              }
            }}>
              Restore Local Draft
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
