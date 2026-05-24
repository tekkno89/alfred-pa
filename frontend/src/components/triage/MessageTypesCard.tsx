import { useState, useEffect } from 'react'
import { Plus, Pencil, Archive, MoreHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  useMessageTypes,
  useCreateMessageType,
  useUpdateMessageType,
  useArchiveMessageType,
} from '@/hooks/useMessageTypes'
import type { MessageType } from '@/types'

interface MessageTypeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  messageType?: MessageType | null
}

function MessageTypeDialog({ open, onOpenChange, messageType }: MessageTypeDialogProps) {
  const [typeName, setTypeName] = useState('')
  const [typeDefinition, setDefinition] = useState('')

  const createMutation = useCreateMessageType()
  const updateMutation = useUpdateMessageType()

  const isEditing = !!messageType

  useEffect(() => {
    if (messageType) {
      setTypeName(messageType.type_name)
      setDefinition(messageType.type_definition)
    } else {
      setTypeName('')
      setDefinition('')
    }
  }, [messageType])

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      setTypeName('')
      setDefinition('')
    }
    onOpenChange(open)
  }

  const handleSave = () => {
    if (!typeName.trim() || !typeDefinition.trim()) return

    if (isEditing && messageType) {
      updateMutation.mutate(
        {
          id: messageType.id,
          data: { type_name: typeName.trim(), type_definition: typeDefinition.trim() },
        },
        {
          onSuccess: () => handleOpenChange(false),
        }
      )
    } else {
      createMutation.mutate(
        { type_name: typeName.trim(), type_definition: typeDefinition.trim() },
        {
          onSuccess: () => handleOpenChange(false),
        }
      )
    }
  }

  const isLoading = createMutation.isPending || updateMutation.isPending

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Message Type' : 'Create Message Type'}</DialogTitle>
          <DialogDescription>
            Define a type of message that Alfred should recognize during triage.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="type-name">Name</Label>
            <Input
              id="type-name"
              placeholder="e.g., Incidents, Action Items, FYIs"
              value={typeName}
              onChange={(e) => setTypeName(e.target.value)}
              maxLength={100}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="type-definition">Definition</Label>
            <Textarea
              id="type-definition"
              placeholder="Describe what this message type means in your workflow..."
              value={typeDefinition}
              onChange={(e) => setDefinition(e.target.value)}
              rows={3}
              maxLength={500}
            />
            <p className="text-xs text-muted-foreground">
              {typeDefinition.length}/500 characters
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={!typeName.trim() || !typeDefinition.trim() || isLoading}
          >
            {isLoading ? 'Saving...' : isEditing ? 'Update' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const SOURCE_LABELS: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' }> = {
  user: { label: 'You', variant: 'default' },
  wizard: { label: 'AI Generated', variant: 'secondary' },
  alfred_suggested: { label: 'Suggested', variant: 'outline' },
}

export function MessageTypesCard() {
  const { data: messageTypes, isLoading, error } = useMessageTypes()
  const archiveMutation = useArchiveMessageType()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingType, setEditingType] = useState<MessageType | null>(null)

  const handleEdit = (type: MessageType) => {
    setEditingType(type)
    setDialogOpen(true)
  }

  const handleArchive = (id: string) => {
    archiveMutation.mutate(id)
  }

  const handleDialogClose = (open: boolean) => {
    setDialogOpen(open)
    if (!open) setEditingType(null)
  }

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          Loading message types...
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-destructive">
          Failed to load message types. Please try again.
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Message Types</CardTitle>
              <CardDescription>
                Define categories of messages for targeted handling rules per channel.
              </CardDescription>
            </div>
            <Button size="sm" onClick={() => setDialogOpen(true)}>
              <Plus className="h-4 w-4 mr-1" />
              Add Type
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {!messageTypes || messageTypes.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <p>No message types defined yet.</p>
              <p className="text-sm mt-1">
                Create message types to set up channel-specific handling rules.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {messageTypes.map((type) => {
                const sourceInfo = SOURCE_LABELS[type.source] ?? SOURCE_LABELS.user
                return (
                  <div
                    key={type.id}
                    className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium truncate">{type.type_name}</span>
                        <Badge variant={sourceInfo.variant} className="text-xs">
                          {sourceInfo.label}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground truncate">
                        {type.type_definition}
                      </p>
                    </div>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => handleEdit(type)}>
                          <Pencil className="h-4 w-4 mr-2" />
                          Edit
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => handleArchive(type.id)}
                          className="text-destructive"
                        >
                          <Archive className="h-4 w-4 mr-2" />
                          Archive
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <MessageTypeDialog
        open={dialogOpen}
        onOpenChange={handleDialogClose}
        messageType={editingType}
      />
    </>
  )
}
