import { useState, useEffect, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Star, Eye, EyeOff, Archive, Trash2, Save, X } from 'lucide-react'
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
import { useNote, useCreateNote, useUpdateNote, useArchiveNote, useDeleteNote } from '@/hooks/useNotes'
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
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [initialized, setInitialized] = useState(false)

  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isSaving = useRef(false)
  const noteIdRef = useRef(noteId)
  noteIdRef.current = noteId

  // Load existing note data
  useEffect(() => {
    if (existingNote && !initialized) {
      setTitle(existingNote.title)
      setBody(existingNote.body)
      setTags(existingNote.tags || [])
      setIsFavorited(existingNote.is_favorited)
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
    const id = noteIdRef.current
    if (!id || isSaving.current) return
    isSaving.current = true
    setSaveStatus('saving')
    updateNote.mutate(
      { id, data: { title, body, is_favorited: isFavorited, tags } },
      {
        onSuccess: () => { isSaving.current = false; setSaveStatus('saved') },
        onError: () => { isSaving.current = false; setSaveStatus('idle') },
      }
    )
  }

  const doCreateRef = useRef<() => void>(() => {})
  doCreateRef.current = () => {
    if (isSaving.current) return
    isSaving.current = true
    setSaveStatus('saving')
    createNote.mutate(
      { title, body, is_favorited: isFavorited, tags },
      {
        onSuccess: (note) => {
          isSaving.current = false
          setSaveStatus('saved')
          navigate(`/notes/${note.id}`, { replace: true })
        },
        onError: () => { isSaving.current = false; setSaveStatus('idle') },
      }
    )
  }

  // Debounced auto-save: triggers 2s after last change to title/body/favorite
  useEffect(() => {
    if (!initialized) return

    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    autoSaveTimer.current = setTimeout(() => {
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

  const handleArchive = async () => {
    if (!noteId) return
    await archiveNote.mutateAsync(noteId)
    navigate('/notes')
  }

  const handleDelete = async () => {
    if (!noteId) return
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
          onClick={() => navigate('/notes')}
          className="h-8 w-8 p-0"
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>

        <span className="text-sm font-medium">
          {isNew ? 'New Note' : 'Edit Note'}
        </span>

        <div className="flex-1" />

        {/* Save status */}
        {saveStatus !== 'idle' && (
          <span className="text-xs text-muted-foreground">
            {saveStatus === 'saving' ? 'Saving...' : 'Saved'}
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
            value={body}
            onChange={(e) => setBody(e.target.value)}
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
                'prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1',
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
    </div>
  )
}
