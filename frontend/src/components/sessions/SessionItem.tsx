import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MessageSquare, Trash2, Hash, Pencil, Check, X, Star } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
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
import { useDeleteSession, useUpdateSession, useToggleSessionStar } from '@/hooks/useSessions'
import type { Session } from '@/types'
import { cn } from '@/lib/utils'

interface SessionItemProps {
  session: Session
  isActive: boolean
}

export function SessionItem({ session, isActive }: SessionItemProps) {
  const navigate = useNavigate()
  const [isEditing, setIsEditing] = useState(false)
  const [editTitle, setEditTitle] = useState(session.title || '')
  const deleteSession = useDeleteSession()
  const updateSession = useUpdateSession()
  const toggleStar = useToggleSessionStar()

  const handleClick = () => {
    if (!isEditing) {
      navigate(`/chat/${session.id}`)
    }
  }

  const handleDelete = async () => {
    await deleteSession.mutateAsync(session.id)
    if (isActive) {
      navigate('/')
    }
  }

  const handleStartEdit = (e: React.MouseEvent) => {
    e.stopPropagation()
    setEditTitle(session.title || '')
    setIsEditing(true)
  }

  const handleSaveEdit = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (editTitle.trim()) {
      await updateSession.mutateAsync({
        id: session.id,
        data: { title: editTitle.trim() },
      })
    }
    setIsEditing(false)
  }

  const handleCancelEdit = (e: React.MouseEvent) => {
    e.stopPropagation()
    setIsEditing(false)
    setEditTitle(session.title || '')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleSaveEdit(e as unknown as React.MouseEvent)
    } else if (e.key === 'Escape') {
      handleCancelEdit(e as unknown as React.MouseEvent)
    }
  }

  const handleToggleStar = (e: React.MouseEvent) => {
    e.stopPropagation()
    toggleStar.mutate(session.id)
  }

  const title = session.title || 'New Chat'

  return (
    <div
      className={cn(
        'group flex items-center gap-2 rounded-md px-2 py-2 cursor-pointer hover:bg-accent',
        isActive && 'bg-accent'
      )}
      onClick={handleClick}
    >
      <MessageSquare className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="flex-1 min-w-0">
        {isEditing ? (
          <Input
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            onKeyDown={handleKeyDown}
            onClick={(e) => e.stopPropagation()}
            className="h-6 text-sm py-0"
            autoFocus
          />
        ) : (
          <div className="flex items-center gap-2">
            <span className="truncate text-sm">{title}</span>
            {session.source === 'slack' && (
              <Badge variant="secondary" className="shrink-0 text-xs py-0 px-1">
                <Hash className="h-3 w-3" />
              </Badge>
            )}
          </div>
        )}
      </div>
      <div className="flex gap-1 shrink-0">
        {isEditing ? (
          <>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={handleSaveEdit}
              disabled={updateSession.isPending}
            >
              <Check className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={handleCancelEdit}
            >
              <X className="h-3 w-3" />
            </Button>
          </>
        ) : (
          <>
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                'h-6 w-6',
                session.is_starred ? 'opacity-100 text-yellow-500' : 'opacity-0 group-hover:opacity-100'
              )}
              onClick={handleToggleStar}
              disabled={toggleStar.isPending}
            >
              <Star className={cn('h-3 w-3', session.is_starred && 'fill-current')} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 opacity-0 group-hover:opacity-100"
              onClick={handleStartEdit}
            >
              <Pencil className="h-3 w-3" />
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 opacity-0 group-hover:opacity-100"
                  onClick={(e) => e.stopPropagation()}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent onClick={(e) => e.stopPropagation()}>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete conversation?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will permanently delete this conversation and all its messages.
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
          </>
        )}
      </div>
    </div>
  )
}
