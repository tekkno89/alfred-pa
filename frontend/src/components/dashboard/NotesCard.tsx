import { useNavigate } from 'react-router-dom'
import { StickyNote, Plus, Star } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { useRecentNotes } from '@/hooks/useNotes'

function formatDate(dateStr: string): string {
  const utcStr = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z'
  return new Date(utcStr).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function NotesCard() {
  const navigate = useNavigate()
  const { data: notes, isLoading } = useRecentNotes()

  return (
    <Card
      className="cursor-pointer hover:shadow-md transition-shadow relative"
      onClick={() => navigate('/notes')}
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <StickyNote className="h-4 w-4" />
          Notes
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : !notes || notes.length === 0 ? (
          <p className="text-sm text-muted-foreground">No notes yet</p>
        ) : (
          <div className="space-y-1.5">
            {notes.map((note) => (
              <div
                key={note.id}
                className="flex items-center justify-between text-sm cursor-pointer hover:bg-muted/50 rounded px-1 -mx-1"
                onClick={(e) => {
                  e.stopPropagation()
                  navigate(`/notes/${note.id}`)
                }}
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  {note.is_favorited && (
                    <Star className="h-3 w-3 fill-yellow-400 text-yellow-400 shrink-0" />
                  )}
                  <span className="truncate">
                    {note.title || 'Untitled'}
                  </span>
                </div>
                <span className="text-xs text-muted-foreground shrink-0 ml-2">
                  {formatDate(note.updated_at)}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
      <button
        className="absolute bottom-3 right-3 h-8 w-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-sm hover:bg-primary/90 transition-colors"
        onClick={(e) => {
          e.stopPropagation()
          navigate('/notes/new')
        }}
      >
        <Plus className="h-6 w-6 stroke-[2.5]" />
      </button>
    </Card>
  )
}
