import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link as RouterLink } from 'react-router-dom'
import { MessageSquare, Link2, Unlink, Bell, Settings, Webhook, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { SlackLinkModal } from '@/components/settings/SlackLinkModal'
import { apiDelete, apiGet, apiPost, ApiRequestError } from '@/lib/api'
import type { SlackStatusResponse, SlackOAuthStatusResponse } from '@/types'

export function SettingsPage() {
  const [linkModalOpen, setLinkModalOpen] = useState(false)
  const [linkError, setLinkError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { data: slackStatus, isLoading: statusLoading } = useQuery({
    queryKey: ['slack-status'],
    queryFn: () => apiGet<SlackStatusResponse>('/auth/slack-status'),
  })

  const { data: oauthStatus, isLoading: oauthLoading } = useQuery({
    queryKey: ['slack-oauth-status'],
    queryFn: () => apiGet<SlackOAuthStatusResponse>('/auth/slack/oauth/status'),
  })

  const revokeOAuthMutation = useMutation({
    mutationFn: () => apiDelete('/auth/slack/oauth'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['slack-oauth-status'] })
    },
  })

  const linkMutation = useMutation({
    mutationFn: (code: string) =>
      apiPost<SlackStatusResponse>('/auth/link-slack', { code }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['slack-status'] })
      setLinkModalOpen(false)
      setLinkError(null)
    },
    onError: (error: Error) => {
      if (error instanceof ApiRequestError) {
        setLinkError(error.detail)
      } else {
        setLinkError('Failed to link Slack account')
      }
    },
  })

  const unlinkMutation = useMutation({
    mutationFn: () => apiPost<SlackStatusResponse>('/auth/unlink-slack'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['slack-status'] })
    },
  })

  const handleLinkSubmit = async (code: string) => {
    setLinkError(null)
    await linkMutation.mutateAsync(code)
  }

  const handleConnectSlackOAuth = async () => {
    try {
      const response = await apiGet<{ url: string }>('/auth/slack/oauth/url')
      window.location.href = response.url
    } catch (error) {
      console.error('Failed to get OAuth URL:', error)
    }
  }

  return (
    <div className="container max-w-2xl py-8">
      <h1 className="text-3xl font-bold mb-6">Settings</h1>

      <div className="space-y-6">
        {/* Focus Mode Settings Card */}
        {oauthStatus?.connected && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-5 w-5" />
                Focus Mode
              </CardTitle>
              <CardDescription>
                Configure auto-reply messages, pomodoro timers, and VIP list.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" asChild>
                <RouterLink to="/settings/focus">
                  <Settings className="h-4 w-4 mr-2" />
                  Configure Focus Mode
                </RouterLink>
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Slack Integration Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MessageSquare className="h-5 w-5" />
              Slack Integration
            </CardTitle>
            <CardDescription>
              Link your Slack account to chat with Alfred directly in Slack.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {statusLoading ? (
              <div className="text-muted-foreground">Loading...</div>
            ) : slackStatus?.linked ? (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm">
                  <div className="h-2 w-2 rounded-full bg-green-500" />
                  <span>Slack account linked</span>
                  <span className="text-muted-foreground">
                    ({slackStatus.slack_user_id})
                  </span>
                </div>
                <Button
                  variant="outline"
                  onClick={() => unlinkMutation.mutate()}
                  disabled={unlinkMutation.isPending}
                >
                  <Unlink className="h-4 w-4 mr-2" />
                  {unlinkMutation.isPending ? 'Unlinking...' : 'Unlink Slack'}
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <div className="h-2 w-2 rounded-full bg-gray-400" />
                  <span>No Slack account linked</span>
                </div>
                <Button onClick={() => setLinkModalOpen(true)}>
                  <Link2 className="h-4 w-4 mr-2" />
                  Link Slack Account
                </Button>
                <p className="text-sm text-muted-foreground">
                  To link your account, type{' '}
                  <code className="bg-muted px-1 rounded">/alfred-link</code> in
                  Slack to get a linking code.
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Slack OAuth Card (for status control) */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ExternalLink className="h-5 w-5" />
              Slack Status Control
            </CardTitle>
            <CardDescription>
              Allow Alfred to update your Slack status when focus mode is enabled.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {oauthLoading ? (
              <div className="text-muted-foreground">Loading...</div>
            ) : oauthStatus?.connected ? (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm">
                  <div className="h-2 w-2 rounded-full bg-green-500" />
                  <span>Slack OAuth connected</span>
                </div>
                <Button
                  variant="outline"
                  onClick={() => revokeOAuthMutation.mutate()}
                  disabled={revokeOAuthMutation.isPending}
                >
                  <Unlink className="h-4 w-4 mr-2" />
                  {revokeOAuthMutation.isPending ? 'Revoking...' : 'Revoke Access'}
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <div className="h-2 w-2 rounded-full bg-gray-400" />
                  <span>Not connected</span>
                </div>
                <Button onClick={handleConnectSlackOAuth}>
                  <Link2 className="h-4 w-4 mr-2" />
                  Connect Slack OAuth
                </Button>
                <p className="text-sm text-muted-foreground">
                  This allows Alfred to set your Slack status to "Focus Mode"
                  when you enable focus mode.
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Webhooks Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Webhook className="h-5 w-5" />
              Webhooks
            </CardTitle>
            <CardDescription>
              Receive notifications about focus mode events on external services.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" asChild>
              <RouterLink to="/settings/webhooks">
                <Settings className="h-4 w-4 mr-2" />
                Manage Webhooks
              </RouterLink>
            </Button>
          </CardContent>
        </Card>
      </div>

      <SlackLinkModal
        open={linkModalOpen}
        onOpenChange={setLinkModalOpen}
        onSubmit={handleLinkSubmit}
        isLoading={linkMutation.isPending}
        error={linkError}
      />
    </div>
  )
}
