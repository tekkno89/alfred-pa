import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { useCreateMemory } from '@/hooks/useMemories'
import type { MemoryType } from '@/types'

interface MemoryFormProps {
  onSuccess?: () => void
}

export function MemoryForm({ onSuccess }: MemoryFormProps) {
  const [type, setType] = useState<MemoryType>('preference')
  const [content, setContent] = useState('')
  const createMemory = useCreateMemory()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!content.trim()) return

    await createMemory.mutateAsync({ type, content: content.trim() })
    setContent('')
    onSuccess?.()
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="type">Type</Label>
        <Select value={type} onValueChange={(value) => setType(value as MemoryType)}>
          <SelectTrigger id="type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="preference">Preference</SelectItem>
            <SelectItem value="knowledge">Knowledge</SelectItem>
            <SelectItem value="summary">Summary</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="content">Content</Label>
        <Textarea
          id="content"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Enter memory content..."
          rows={3}
        />
      </div>
      <Button type="submit" disabled={!content.trim() || createMemory.isPending}>
        {createMemory.isPending ? 'Adding...' : 'Add Memory'}
      </Button>
    </form>
  )
}
