import { useState, useEffect } from 'react'
import { Settings, Save, Bell, Volume2, Play } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { VipList } from '@/components/focus/VipList'
import { useFocusSettings, useUpdateFocusSettings } from '@/hooks/useFocusMode'
import { useAlertSound } from '@/hooks/useAlertSound'
import type { BypassNotificationConfig } from '@/types'

const DEFAULT_CONFIG: BypassNotificationConfig = {
  alfred_ui_enabled: true,
  email_enabled: false,
  email_address: null,
  sms_enabled: false,
  phone_number: null,
  alert_sound_enabled: true,
  alert_sound_name: 'chime',
  alert_title_flash_enabled: true,
}

const SOUND_OPTIONS = [
  { value: 'chime', label: 'Chime' },
  { value: 'urgent', label: 'Urgent Alarm' },
  { value: 'gentle', label: 'Gentle Bell' },
  { value: 'ping', label: 'Notification Ping' },
]

export function FocusSettingsPage() {
  const { data: settings, isLoading } = useFocusSettings()
  const updateMutation = useUpdateFocusSettings()
  const { playAlertSound } = useAlertSound()

  const [defaultMessage, setDefaultMessage] = useState('')
  const [notifyConfig, setNotifyConfig] = useState<BypassNotificationConfig>(DEFAULT_CONFIG)
  const [hasMessageChanges, setHasMessageChanges] = useState(false)
  const [hasNotifyChanges, setHasNotifyChanges] = useState(false)

  // Load settings into form
  useEffect(() => {
    if (settings) {
      setDefaultMessage(settings.default_message || '')
      setNotifyConfig(settings.bypass_notification_config ?? DEFAULT_CONFIG)
    }
  }, [settings])

  // Track message changes
  useEffect(() => {
    if (!settings) return
    setHasMessageChanges(defaultMessage !== (settings.default_message || ''))
  }, [defaultMessage, settings])

  // Track notification config changes
  useEffect(() => {
    if (!settings) return
    const saved = settings.bypass_notification_config ?? DEFAULT_CONFIG
    setHasNotifyChanges(JSON.stringify(notifyConfig) !== JSON.stringify(saved))
  }, [notifyConfig, settings])

  const handleSaveMessage = async () => {
    await updateMutation.mutateAsync({
      default_message: defaultMessage || null,
    })
    setHasMessageChanges(false)
  }

  const handleSaveNotifyConfig = async () => {
    await updateMutation.mutateAsync({
      bypass_notification_config: notifyConfig,
    })
    setHasNotifyChanges(false)
  }

  const updateConfig = (updates: Partial<BypassNotificationConfig>) => {
    setNotifyConfig((prev) => ({ ...prev, ...updates }))
  }

  if (isLoading) {
    return (
      <div className="container max-w-2xl py-8">
        <div className="text-center text-muted-foreground">Loading settings...</div>
      </div>
    )
  }

  return (
    <div className="container max-w-2xl py-8">
      <h1 className="text-3xl font-bold mb-6">Focus Mode Settings</h1>

      <div className="space-y-6">
        {/* General Settings */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5" />
              Auto-Reply Message
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="defaultMessage">Default Message</Label>
              <Textarea
                id="defaultMessage"
                placeholder="I'm currently in focus mode and not available. I'll respond when I'm back."
                value={defaultMessage}
                onChange={(e) => setDefaultMessage(e.target.value)}
                rows={3}
              />
              <p className="text-sm text-muted-foreground">
                This message will be sent to people who try to reach you during focus mode.
              </p>
            </div>

            {/* Save button */}
            {hasMessageChanges && (
              <div className="flex justify-end">
                <Button onClick={handleSaveMessage} disabled={updateMutation.isPending}>
                  <Save className="h-4 w-4 mr-2" />
                  {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Bypass Notification Settings */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bell className="h-5 w-5" />
              Bypass Notification Settings
            </CardTitle>
            <CardDescription>
              Configure how you're notified when someone bypasses your focus mode.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Alfred UI */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-base">Alfred UI</Label>
                  <p className="text-sm text-muted-foreground">
                    Show notifications in the browser
                  </p>
                </div>
                <Switch
                  checked={notifyConfig.alfred_ui_enabled}
                  onCheckedChange={(checked) => updateConfig({ alfred_ui_enabled: checked })}
                />
              </div>

              {notifyConfig.alfred_ui_enabled && (
                <div className="ml-6 space-y-4 border-l-2 border-muted pl-4">
                  {/* Alert sound */}
                  <div className="flex items-center justify-between">
                    <div>
                      <Label>Play alert sound</Label>
                      <p className="text-xs text-muted-foreground">
                        Play a sound when a bypass notification arrives
                      </p>
                    </div>
                    <Switch
                      checked={notifyConfig.alert_sound_enabled}
                      onCheckedChange={(checked) =>
                        updateConfig({ alert_sound_enabled: checked })
                      }
                    />
                  </div>

                  {notifyConfig.alert_sound_enabled && (
                    <div className="flex items-center gap-2">
                      <Select
                        value={notifyConfig.alert_sound_name}
                        onValueChange={(value) => updateConfig({ alert_sound_name: value })}
                      >
                        <SelectTrigger className="w-48">
                          <Volume2 className="h-4 w-4 mr-2 shrink-0" />
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {SOUND_OPTIONS.map((opt) => (
                            <SelectItem key={opt.value} value={opt.value}>
                              {opt.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => playAlertSound(notifyConfig.alert_sound_name)}
                      >
                        <Play className="h-3 w-3 mr-1" />
                        Preview
                      </Button>
                    </div>
                  )}

                  {/* Title flash */}
                  <div className="flex items-center justify-between">
                    <div>
                      <Label>Flash browser tab</Label>
                      <p className="text-xs text-muted-foreground">
                        Alternate the browser tab title to get your attention
                      </p>
                    </div>
                    <Switch
                      checked={notifyConfig.alert_title_flash_enabled}
                      onCheckedChange={(checked) =>
                        updateConfig({ alert_title_flash_enabled: checked })
                      }
                    />
                  </div>
                </div>
              )}
            </div>

            <div className="border-t pt-4" />

            {/* Email */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div>
                    <Label className="text-base">Email</Label>
                    <p className="text-sm text-muted-foreground">
                      Send bypass alerts to your email
                    </p>
                  </div>
                  <Badge variant="secondary" className="text-xs">
                    Coming soon
                  </Badge>
                </div>
                <Switch
                  checked={notifyConfig.email_enabled}
                  onCheckedChange={(checked) => updateConfig({ email_enabled: checked })}
                />
              </div>

              {notifyConfig.email_enabled && (
                <div className="ml-6 border-l-2 border-muted pl-4">
                  <Label htmlFor="email_address">Email address</Label>
                  <Input
                    id="email_address"
                    type="email"
                    placeholder="you@example.com"
                    value={notifyConfig.email_address || ''}
                    onChange={(e) => updateConfig({ email_address: e.target.value || null })}
                    className="mt-1"
                  />
                </div>
              )}
            </div>

            <div className="border-t pt-4" />

            {/* SMS */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div>
                    <Label className="text-base">SMS</Label>
                    <p className="text-sm text-muted-foreground">
                      Send bypass alerts via text message
                    </p>
                  </div>
                  <Badge variant="secondary" className="text-xs">
                    Coming soon
                  </Badge>
                </div>
                <Switch
                  checked={notifyConfig.sms_enabled}
                  onCheckedChange={(checked) => updateConfig({ sms_enabled: checked })}
                />
              </div>

              {notifyConfig.sms_enabled && (
                <div className="ml-6 border-l-2 border-muted pl-4">
                  <Label htmlFor="phone_number">Phone number</Label>
                  <Input
                    id="phone_number"
                    type="tel"
                    placeholder="+1 (555) 123-4567"
                    value={notifyConfig.phone_number || ''}
                    onChange={(e) => updateConfig({ phone_number: e.target.value || null })}
                    className="mt-1"
                  />
                </div>
              )}
            </div>

            {/* Save button */}
            {hasNotifyChanges && (
              <div className="flex justify-end pt-2">
                <Button onClick={handleSaveNotifyConfig} disabled={updateMutation.isPending}>
                  <Save className="h-4 w-4 mr-2" />
                  {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* VIP List */}
        <VipList />
      </div>
    </div>
  )
}
