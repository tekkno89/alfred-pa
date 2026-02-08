import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Webhook, Trash2, Power, PowerOff, TestTube } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { WebhookForm } from '@/components/settings/WebhookForm'
import { apiDelete, apiGet, apiPost, apiPut } from '@/lib/api'
import type {
  WebhookCreateRequest,
  WebhookEventType,
  WebhookListResponse,
  WebhookResponse,
  WebhookTestResponse,
} from '@/types'

export function WebhooksPage() {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['webhooks'],
    queryFn: () => apiGet<WebhookListResponse>('/webhooks'),
  })

  const createMutation = useMutation({
    mutationFn: (data: WebhookCreateRequest) =>
      apiPost<WebhookResponse>('/webhooks', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['webhooks'] })
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      apiPut<WebhookResponse>(`/webhooks/${id}`, { enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['webhooks'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiDelete(`/webhooks/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['webhooks'] })
    },
  })

  const testMutation = useMutation({
    mutationFn: (id: string) =>
      apiPost<WebhookTestResponse>(`/webhooks/${id}/test`, {
        event_type: 'focus_bypass',
      }),
  })

  const handleCreate = (formData: {
    name: string
    url: string
    event_types: WebhookEventType[]
  }) => {
    createMutation.mutate(formData)
  }

  return (
    <div className="container max-w-2xl py-8">
      <h1 className="text-3xl font-bold mb-6">Webhook Settings</h1>

      <div className="space-y-6">
        {/* Add Webhook */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Webhook className="h-5 w-5" />
              Add Webhook
            </CardTitle>
            <CardDescription>
              Receive notifications when focus mode events occur.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <WebhookForm
              onSubmit={handleCreate}
              isLoading={createMutation.isPending}
            />
          </CardContent>
        </Card>

        {/* Webhook List */}
        <Card>
          <CardHeader>
            <CardTitle>Your Webhooks</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="text-center text-muted-foreground py-4">
                Loading...
              </div>
            ) : data?.webhooks.length === 0 ? (
              <div className="text-center text-muted-foreground py-4">
                No webhooks configured yet.
              </div>
            ) : (
              <ul className="space-y-3">
                {data?.webhooks.map((webhook) => (
                  <li
                    key={webhook.id}
                    className={`p-4 rounded-lg border ${
                      webhook.enabled
                        ? 'border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-950'
                        : 'border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-950'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{webhook.name}</span>
                          <span
                            className={`text-xs px-2 py-0.5 rounded-full ${
                              webhook.enabled
                                ? 'bg-green-200 text-green-800 dark:bg-green-800 dark:text-green-200'
                                : 'bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
                            }`}
                          >
                            {webhook.enabled ? 'Active' : 'Disabled'}
                          </span>
                        </div>
                        <div className="text-sm text-muted-foreground truncate mt-1">
                          {webhook.url}
                        </div>
                        <div className="flex flex-wrap gap-1 mt-2">
                          {webhook.event_types.map((event) => (
                            <span
                              key={event}
                              className="text-xs px-2 py-0.5 rounded bg-muted"
                            >
                              {event}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="flex gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            toggleMutation.mutate({
                              id: webhook.id,
                              enabled: !webhook.enabled,
                            })
                          }
                          title={webhook.enabled ? 'Disable' : 'Enable'}
                        >
                          {webhook.enabled ? (
                            <PowerOff className="h-4 w-4" />
                          ) : (
                            <Power className="h-4 w-4" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => testMutation.mutate(webhook.id)}
                          disabled={testMutation.isPending}
                          title="Test webhook"
                        >
                          <TestTube className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => deleteMutation.mutate(webhook.id)}
                          disabled={deleteMutation.isPending}
                          title="Delete"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
