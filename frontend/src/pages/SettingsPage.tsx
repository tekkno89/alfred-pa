import { useQuery } from '@tanstack/react-query'
import { Link as RouterLink } from 'react-router-dom'
import { Bell, Settings, Webhook, Plug } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { apiGet } from '@/lib/api'
import type { SlackOAuthStatusResponse } from '@/types'

export function SettingsPage() {
  const { data: oauthStatus } = useQuery({
    queryKey: ['slack-oauth-status'],
    queryFn: () => apiGet<SlackOAuthStatusResponse>('/auth/slack/oauth/status'),
  })

  return (
    <div className="h-full overflow-y-auto">
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
              <RouterLink to="/settings/focus">
                <Button variant="outline">
                  <Settings className="h-4 w-4 mr-2" />
                  Configure Focus Mode
                </Button>
              </RouterLink>
            </CardContent>
          </Card>
        )}

        {/* Integrations Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Plug className="h-5 w-5" />
              Integrations
            </CardTitle>
            <CardDescription>
              Manage connections to GitHub, Slack, and other services.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <RouterLink to="/settings/integrations">
              <Button variant="outline">
                <Settings className="h-4 w-4 mr-2" />
                Manage Integrations
              </Button>
            </RouterLink>
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
            <RouterLink to="/settings/webhooks">
              <Button variant="outline">
                <Settings className="h-4 w-4 mr-2" />
                Manage Webhooks
              </Button>
            </RouterLink>
          </CardContent>
        </Card>
      </div>
    </div>
    </div>
  )
}
