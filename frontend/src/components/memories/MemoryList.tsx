import { MemoryItem } from './MemoryItem'
import type { Memory } from '@/types'

interface MemoryListProps {
  memories: Memory[]
  isLoading: boolean
}

export function MemoryList({ memories, isLoading }: MemoryListProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        {[...Array(3)].map((_, i) => (
          <div
            key={i}
            className="h-24 rounded-lg bg-muted animate-pulse"
          />
        ))}
      </div>
    )
  }

  if (memories.length === 0) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        <p className="text-lg font-medium">No memories yet</p>
        <p className="text-sm">
          Memories are extracted from your conversations or can be added manually
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {memories.map((memory) => (
        <MemoryItem key={memory.id} memory={memory} />
      ))}
    </div>
  )
}
