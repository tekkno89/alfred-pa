import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Pencil, Trash2, X, Check, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
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
import { useUpdateMemory, useDeleteMemory } from '@/hooks/useMemories'
import type { Memory } from '@/types'

interface MemoryItemProps {
  memory: Memory
}

export function MemoryItem({ memory }: MemoryItemProps) {
  const navigate = useNavigate()
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState(memory.content)
  const updateMemory = useUpdateMemory()
  const deleteMemory = useDeleteMemory()

  const handleSave = async () => {
    if (!editContent.trim()) return
    await updateMemory.mutateAsync({
      id: memory.id,
      data: { content: editContent.trim() },
    })
    setIsEditing(false)
  }

  const handleCancel = () => {
    setEditContent(memory.content)
    setIsEditing(false)
  }

  const handleDelete = async () => {
    await deleteMemory.mutateAsync(memory.id)
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  }

  const getBadgeVariant = (type: string) => {
    switch (type) {
      case 'preference':
        return 'default'
      case 'knowledge':
        return 'secondary'
      case 'summary':
        return 'outline'
      default:
        return 'default'
    }
  }

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <Badge variant={getBadgeVariant(memory.type)}>
                {memory.type}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {formatDate(memory.updated_at)}
              </span>
            </div>
            {isEditing ? (
              <Textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                rows={3}
                className="mb-2"
              />
            ) : (
              <p className="text-sm whitespace-pre-wrap">{memory.content}</p>
            )}
            {memory.source_session_id && !isEditing && (
              <Button
                variant="link"
                size="sm"
                className="p-0 h-auto mt-2"
                onClick={() => navigate(`/chat/${memory.source_session_id}`)}
              >
                <ExternalLink className="h-3 w-3 mr-1" />
                View source conversation
              </Button>
            )}
          </div>
          <div className="flex gap-1 shrink-0">
            {isEditing ? (
              <>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleSave}
                  disabled={updateMemory.isPending}
                >
                  <Check className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="icon" onClick={handleCancel}>
                  <X className="h-4 w-4" />
                </Button>
              </>
            ) : (
              <>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setIsEditing(true)}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="ghost" size="icon">
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Delete memory?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This will permanently delete this memory.
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
      </CardContent>
    </Card>
  )
}
