import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link as RouterLink } from 'react-router-dom'
import { Bell, Settings, Webhook, Plug, Clock, Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { apiGet, apiPatch } from '@/lib/api'
import { useAuthStore } from '@/lib/auth'
import type { SlackOAuthStatusResponse, User, UserUpdate } from '@/types'
import { useState, useEffect } from 'react'

const TIMEZONES = [
  { value: 'UTC', label: 'UTC' },
  { group: 'Americas', items: [
    { value: 'America/New_York', label: 'Eastern Time (US)' },
    { value: 'America/Chicago', label: 'Central Time (US)' },
    { value: 'America/Denver', label: 'Mountain Time (US)' },
    { value: 'America/Los_Angeles', label: 'Pacific Time (US)' },
    { value: 'America/Anchorage', label: 'Alaska Time' },
    { value: 'Pacific/Honolulu', label: 'Hawaii Time' },
    { value: 'America/Toronto', label: 'Toronto' },
    { value: 'America/Vancouver', label: 'Vancouver' },
    { value: 'America/Mexico_City', label: 'Mexico City' },
    { value: 'America/Sao_Paulo', label: 'Sao Paulo' },
    { value: 'America/Buenos_Aires', label: 'Buenos Aires' },
  ]},
  { group: 'Europe', items: [
    { value: 'Europe/London', label: 'London' },
    { value: 'Europe/Paris', label: 'Paris' },
    { value: 'Europe/Berlin', label: 'Berlin' },
    { value: 'Europe/Madrid', label: 'Madrid' },
    { value: 'Europe/Rome', label: 'Rome' },
    { value: 'Europe/Amsterdam', label: 'Amsterdam' },
    { value: 'Europe/Stockholm', label: 'Stockholm' },
    { value: 'Europe/Moscow', label: 'Moscow' },
  ]},
  { group: 'Asia', items: [
    { value: 'Asia/Tokyo', label: 'Tokyo' },
    { value: 'Asia/Shanghai', label: 'Shanghai' },
    { value: 'Asia/Hong_Kong', label: 'Hong Kong' },
    { value: 'Asia/Singapore', label: 'Singapore' },
    { value: 'Asia/Seoul', label: 'Seoul' },
    { value: 'Asia/Mumbai', label: 'Mumbai' },
    { value: 'Asia/Dubai', label: 'Dubai' },
    { value: 'Asia/Bangkok', label: 'Bangkok' },
  ]},
  { group: 'Pacific', items: [
    { value: 'Australia/Sydney', label: 'Sydney' },
    { value: 'Australia/Melbourne', label: 'Melbourne' },
    { value: 'Australia/Perth', label: 'Perth' },
    { value: 'Pacific/Auckland', label: 'Auckland' },
  ]},
]

export function SettingsPage() {
  const queryClient = useQueryClient()
  const setUser = useAuthStore((state) => state.setUser)
  const user = useAuthStore((state) => state.user)
  
  const { data: oauthStatus } = useQuery({
    queryKey: ['slack-oauth-status'],
    queryFn: () => apiGet<SlackOAuthStatusResponse>('/auth/slack/oauth/status'),
  })

  const { data: userProfile } = useQuery({
    queryKey: ['user-profile'],
    queryFn: () => apiGet<User>('/auth/me'),
  })

  const [selectedTimezone, setSelectedTimezone] = useState<string>('')

  useEffect(() => {
    if (userProfile?.timezone) {
      setSelectedTimezone(userProfile.timezone)
    } else if (user?.timezone) {
      setSelectedTimezone(user.timezone)
    }
  }, [userProfile, user])

  const updateProfile = useMutation({
    mutationFn: (data: UserUpdate) => apiPatch<User>('/auth/me', data),
    onSuccess: (updatedUser) => {
      setUser(updatedUser)
      queryClient.setQueryData(['user-profile'], updatedUser)
    },
  })

  const handleSaveTimezone = () => {
    if (selectedTimezone) {
      updateProfile.mutate({ timezone: selectedTimezone })
    }
  }

  const currentTimezone = userProfile?.timezone || user?.timezone || 'UTC'

  return (
    <div className="h-full overflow-y-auto">
    <div className="container max-w-2xl py-8">
      <h1 className="text-3xl font-bold mb-6">Settings</h1>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Profile
            </CardTitle>
            <CardDescription>
              Your timezone is used for scheduling digests and reminders.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="timezone">Timezone</Label>
              <Select value={selectedTimezone} onValueChange={setSelectedTimezone}>
                <SelectTrigger id="timezone" className="w-full">
                  <SelectValue placeholder="Select timezone" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="UTC">UTC</SelectItem>
                  {TIMEZONES.filter((t): t is { group: string; items: { value: string; label: string }[] } => 'items' in t).map((group) => (
                    <optgroup key={group.group} label={group.group}>
                      {group.items.map((tz) => (
                        <SelectItem key={tz.value} value={tz.value}>
                          {tz.label}
                        </SelectItem>
                      ))}
                    </optgroup>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <Button 
                onClick={handleSaveTimezone}
                disabled={updateProfile.isPending || selectedTimezone === currentTimezone}
              >
                <Save className="h-4 w-4 mr-2" />
                {updateProfile.isPending ? 'Saving...' : 'Save Timezone'}
              </Button>
              {updateProfile.isSuccess && (
                <span className="text-sm text-green-600">Saved!</span>
              )}
            </div>
          </CardContent>
        </Card>

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
