import { useState } from 'react'
import { Select } from '@/components/ui/select'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { MemoryList } from '@/components/memories/MemoryList'
import { MemoryForm } from '@/components/memories/MemoryForm'
import { useMemories } from '@/hooks/useMemories'
import type { MemoryType } from '@/types'

export function MemoriesPage() {
  const [typeFilter, setTypeFilter] = useState<MemoryType | ''>('')
  const { data, isLoading } = useMemories(
    1,
    50,
    typeFilter || undefined
  )

  return (
    <div className="h-full overflow-auto p-6">
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Memories</h1>
          <p className="text-muted-foreground">
            Manage what Alfred remembers about you
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Add Memory</CardTitle>
          </CardHeader>
          <CardContent>
            <MemoryForm />
          </CardContent>
        </Card>

        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Your Memories</h2>
          <Select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as MemoryType | '')}
            className="w-40"
          >
            <option value="">All types</option>
            <option value="preference">Preference</option>
            <option value="knowledge">Knowledge</option>
            <option value="summary">Summary</option>
          </Select>
        </div>

        <MemoryList
          memories={data?.items || []}
          isLoading={isLoading}
        />
      </div>
    </div>
  )
}
