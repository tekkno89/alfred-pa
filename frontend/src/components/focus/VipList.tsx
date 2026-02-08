import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, UserCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { apiDelete, apiGet, apiPost } from '@/lib/api'
import type { VIPAddRequest, VIPListResponse, VIPResponse } from '@/types'

export function VipList() {
  const [newSlackId, setNewSlackId] = useState('')
  const [newDisplayName, setNewDisplayName] = useState('')
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['focus-vip-list'],
    queryFn: () => apiGet<VIPListResponse>('/focus/vip'),
  })

  const addMutation = useMutation({
    mutationFn: (data: VIPAddRequest) => apiPost<VIPResponse>('/focus/vip', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['focus-vip-list'] })
      setNewSlackId('')
      setNewDisplayName('')
    },
  })

  const removeMutation = useMutation({
    mutationFn: (id: string) => apiDelete(`/focus/vip/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['focus-vip-list'] })
    },
  })

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newSlackId.trim()) return

    await addMutation.mutateAsync({
      slack_user_id: newSlackId.trim(),
      display_name: newDisplayName.trim() || undefined,
    })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserCheck className="h-5 w-5" />
          VIP Whitelist
        </CardTitle>
        <CardDescription>
          These Slack users can bypass your focus mode and reach you directly.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {/* Add form */}
        <form onSubmit={handleAdd} className="flex gap-2 mb-4">
          <Input
            placeholder="Slack User ID (e.g., U12345678)"
            value={newSlackId}
            onChange={(e) => setNewSlackId(e.target.value)}
            className="flex-1"
          />
          <Input
            placeholder="Display name (optional)"
            value={newDisplayName}
            onChange={(e) => setNewDisplayName(e.target.value)}
            className="flex-1"
          />
          <Button type="submit" disabled={addMutation.isPending || !newSlackId.trim()}>
            <Plus className="h-4 w-4 mr-2" />
            Add
          </Button>
        </form>

        {/* List */}
        {isLoading ? (
          <div className="text-center text-muted-foreground py-4">Loading...</div>
        ) : data?.vips.length === 0 ? (
          <div className="text-center text-muted-foreground py-4">
            No VIP users added yet.
          </div>
        ) : (
          <ul className="space-y-2">
            {data?.vips.map((vip) => (
              <li
                key={vip.id}
                className="flex items-center justify-between p-2 rounded bg-muted"
              >
                <div>
                  <span className="font-medium">
                    {vip.display_name || vip.slack_user_id}
                  </span>
                  {vip.display_name && (
                    <span className="text-sm text-muted-foreground ml-2">
                      ({vip.slack_user_id})
                    </span>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeMutation.mutate(vip.id)}
                  disabled={removeMutation.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
