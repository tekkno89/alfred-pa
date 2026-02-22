import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { StickyNote, Plus, ArrowLeft, Star, Archive, RotateCcw, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
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
import { useNotes, useUpdateNote, useRestoreNote, useDeleteNote } from '@/hooks/useNotes'
import { cn } from '@/lib/utils'

function formatDate(dateStr: string): string {
  const utcStr = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z'
  return new Date(utcStr).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function NotesPage() {
  const navigate = useNavigate()
  const [showArchived, setShowArchived] = useState(false)
  const { data, isLoading } = useNotes(1, 100, 'updated_at', showArchived)
  const updateNote = useUpdateNote()
  const restoreNote = useRestoreNote()
  const deleteNote = useDeleteNote()

  const toggleFavorite = (noteId: string, currentFav: boolean) => {
    updateNote.mutate({ id: noteId, data: { is_favorited: !currentFav } })
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto p-4 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/')}
              className="h-8 w-8 p-0"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div className="flex items-center gap-2">
              <StickyNote className="h-5 w-5" />
              <h1 className="text-xl font-semibold">Notes</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant={showArchived ? 'default' : 'outline'}
              size="sm"
              onClick={() => setShowArchived(!showArchived)}
              className="text-xs"
            >
              <Archive className="h-3.5 w-3.5 mr-1" />
              {showArchived ? 'Showing Archived' : 'Show Archived'}
            </Button>
            <Button size="sm" onClick={() => navigate('/notes/new')}>
              <Plus className="h-4 w-4 mr-1" />
              New Note
            </Button>
          </div>
        </div>

        {/* Notes list */}
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : !data?.items.length ? (
          <div className="text-center py-12 space-y-2">
            <StickyNote className="h-10 w-10 mx-auto text-muted-foreground" />
            <p className="text-muted-foreground">
              {showArchived ? 'No archived notes' : 'No notes yet'}
            </p>
            {!showArchived && (
              <Button variant="outline" size="sm" onClick={() => navigate('/notes/new')}>
                Create your first note
              </Button>
            )}
          </div>
        ) : (
          <div className="space-y-1">
            <div className="flex items-center gap-2 px-2 pb-1 border-b text-xs font-medium text-muted-foreground">
              {!showArchived && <div className="w-7 shrink-0" />}
              <div className="flex-1">Note</div>
              <div className="w-40 shrink-0">Tags</div>
              <div className="shrink-0">Last Updated</div>
              {showArchived && <div className="w-16" />}
            </div>
            {data.items.map((note) => (
              <div
                key={note.id}
                className="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 cursor-pointer group"
                onClick={() => navigate(`/notes/${note.id}`)}
              >
                {/* Star toggle */}
                {!showArchived && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0 shrink-0"
                    onClick={(e) => {
                      e.stopPropagation()
                      toggleFavorite(note.id, note.is_favorited)
                    }}
                  >
                    <Star
                      className={cn(
                        'h-4 w-4',
                        note.is_favorited
                          ? 'fill-yellow-400 text-yellow-400'
                          : 'text-muted-foreground'
                      )}
                    />
                  </Button>
                )}

                {/* Title */}
                <div className="flex-1 min-w-0">
                  <span className="text-sm truncate block">
                    {note.title || 'Untitled'}
                  </span>
                </div>

                {/* Tags */}
                <div className="w-40 shrink-0 flex flex-wrap gap-1">
                  {note.tags?.map((tag) => (
                    <span
                      key={tag}
                      className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-muted text-muted-foreground"
                    >
                      {tag}
                    </span>
                  ))}
                </div>

                <span className="text-xs text-muted-foreground shrink-0">
                  {formatDate(note.updated_at)}
                </span>

                {/* Archived actions */}
                {showArchived && (
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      onClick={(e) => {
                        e.stopPropagation()
                        restoreNote.mutate(note.id)
                      }}
                      title="Restore"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                    </Button>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                          onClick={(e) => e.stopPropagation()}
                          title="Delete permanently"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent onClick={(e) => e.stopPropagation()}>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Delete note permanently?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This action cannot be undone. The note will be permanently deleted.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => deleteNote.mutate(note.id)}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                          >
                            Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
