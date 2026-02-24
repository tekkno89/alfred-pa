import { useState } from 'react'
import { Shield, ArrowLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useAuthStore } from '@/lib/auth'
import { useAdminUsers, useUpdateUserRole, useUserFeatures, useSetFeatureAccess, useSystemSettings, useUpdateSystemSetting } from '@/hooks/useAdmin'
import type { AdminUser } from '@/types'

const FEATURE_KEYS = ['card:bart', 'card:notes'] as const

function UserFeatureToggles({ user }: { user: AdminUser }) {
  const { data: features } = useUserFeatures(user.id)
  const setAccess = useSetFeatureAccess()

  const isFeatureEnabled = (featureKey: string) => {
    const entry = features?.find((f) => f.feature_key === featureKey)
    return entry?.enabled ?? false
  }

  const toggleFeature = (featureKey: string) => {
    const current = isFeatureEnabled(featureKey)
    setAccess.mutate({
      userId: user.id,
      featureKey,
      data: { enabled: !current },
    })
  }

  return (
    <div className="flex gap-2 flex-wrap">
      {FEATURE_KEYS.map((key) => {
        const enabled = isFeatureEnabled(key)
        return (
          <Button
            key={key}
            variant={enabled ? 'default' : 'outline'}
            size="sm"
            className={`text-xs h-7 ${enabled ? 'bg-green-600 hover:bg-green-700' : ''}`}
            onClick={() => toggleFeature(key)}
          >
            {key}
          </Button>
        )
      })}
    </div>
  )
}

function UserRow({ user }: { user: AdminUser }) {
  const updateRole = useUpdateUserRole()
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="border rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{user.email}</span>
          <Badge variant={user.role === 'admin' ? 'default' : 'secondary'}>
            {user.role}
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={user.role}
            onValueChange={(role) =>
              updateRole.mutate({
                userId: user.id,
                data: { role: role as 'admin' | 'user' },
              })
            }
          >
            <SelectTrigger className="w-24 h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="user">User</SelectItem>
              <SelectItem value="admin">Admin</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="ghost"
            size="sm"
            className="text-xs h-8"
            onClick={() => setExpanded(!expanded)}
          >
            Features
          </Button>
        </div>
      </div>
      {expanded && (
        <div className="pt-1">
          <UserFeatureToggles user={user} />
        </div>
      )}
    </div>
  )
}

function SystemSettingsCard() {
  const { data: settings, isLoading } = useSystemSettings()
  const updateSetting = useUpdateSystemSetting()

  const autoReplyEnabled = settings?.find(
    (s) => s.key === 'focus_auto_reply_enabled'
  )?.value === 'true'

  const handleToggle = (checked: boolean) => {
    updateSetting.mutate({
      key: 'focus_auto_reply_enabled',
      data: { value: checked ? 'true' : 'false' },
    })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>System Settings</CardTitle>
        <CardDescription>Global settings that affect all users</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading settings...</p>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="focus-auto-reply">Focus mode auto-reply</Label>
                <p className="text-xs text-muted-foreground">
                  Send auto-reply messages when someone DMs or @mentions a user in focus mode
                </p>
              </div>
              <Switch
                id="focus-auto-reply"
                checked={autoReplyEnabled}
                onCheckedChange={handleToggle}
                disabled={updateSetting.isPending}
              />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function AdminPage() {
  const navigate = useNavigate()
  const currentUser = useAuthStore((state) => state.user)
  const { data, isLoading } = useAdminUsers()

  if (currentUser?.role !== 'admin') {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-2">
          <Shield className="h-10 w-10 mx-auto text-muted-foreground" />
          <p className="text-lg font-medium">Access Denied</p>
          <p className="text-sm text-muted-foreground">
            You need admin privileges to access this page.
          </p>
          <Button variant="outline" onClick={() => navigate('/')}>
            Go Home
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto p-4 space-y-4">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/')}
            className="h-8 w-8 p-0"
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            <h1 className="text-xl font-semibold">Admin</h1>
          </div>
        </div>

        <SystemSettingsCard />

        <Card>
          <CardHeader>
            <CardTitle>Users</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <p className="text-sm text-muted-foreground">Loading users...</p>
            ) : !data?.items.length ? (
              <p className="text-sm text-muted-foreground">No users found.</p>
            ) : (
              <div className="space-y-2">
                {data.items.map((user) => (
                  <UserRow key={user.id} user={user} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
