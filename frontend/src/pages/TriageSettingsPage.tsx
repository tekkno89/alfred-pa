import { useState, useMemo, useEffect } from 'react'
import { ArrowLeft, Plus, Trash2, Hash, Lock, RefreshCw, Sparkles, Settings } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import {
  useTriageSettings,
  useUpdateTriageSettings,
  useMonitoredChannels,
  useUpdateMonitoredChannel,
  useRefreshSlackChannels,
  useAutoEnrollChannels,
} from '@/hooks/useTriage'
import { useNotificationContext } from '@/components/notifications/NotificationProvider'
import { ClassifierWizardModal } from '@/components/triage/ClassifierWizardModal'
import { ChannelConfigModal } from '@/components/triage/ChannelConfigModal'
import type { MonitoredChannel, ChannelPriority } from '@/types'

const DEFAULT_P0 = 'Needs immediate attention RIGHT NOW. Production incidents, emergencies, someone explicitly saying something is urgent/critical.'
const DEFAULT_P1 = 'Time-sensitive requests that need action soon. Direct asks requiring a response, important questions needing input.'
const DEFAULT_P2 = 'Noteworthy but not time-sensitive. Project updates, FYI items, relevant discussions worth reviewing later.'
const DEFAULT_P3 = 'Low priority. General chatter, memes, social messages, automated notifications that need no action.'

export function TriageSettingsPage() {
  const navigate = useNavigate()
  const { data: settings, isLoading: settingsLoading } = useTriageSettings()
  const updateSettings = useUpdateTriageSettings()
  const { data: channelData, isLoading: channelsLoading } = useMonitoredChannels()
  const updateChannel = useUpdateMonitoredChannel()
  const refreshChannels = useRefreshSlackChannels()

  // Wire SSE events to the refresh hook so it knows when the job finishes
  const { lastEvent } = useNotificationContext()
  useEffect(() => {
    if (lastEvent) {
      refreshChannels.onNotification(lastEvent)
    }
  }, [lastEvent]) // eslint-disable-line react-hooks/exhaustive-deps

  const [customRules, setCustomRules] = useState<string | null>(null)
  const [wizardOpen, setWizardOpen] = useState(false)

  // Channel configuration modal state
  const [configChannel, setConfigChannel] = useState<MonitoredChannel | null>(null)
  const [configModalOpen, setConfigModalOpen] = useState(false)
  const [showHiddenChannels, setShowHiddenChannels] = useState(false)

  // Auto-enroll
  const autoEnroll = useAutoEnrollChannels()

  // Priority definition local state
  const [p0Def, setP0Def] = useState<string | null>(null)
  const [p1Def, setP1Def] = useState<string | null>(null)
  const [p2Def, setP2Def] = useState<string | null>(null)
  const [p3Def, setP3Def] = useState<string | null>(null)
  const [digestInstr, setDigestInstr] = useState<string | null>(null)

  // Alert cadence mode state
  const [p1Mode, setP1Mode] = useState<'interval' | 'scheduled'>(
    (settings?.p1_digest_interval_minutes ? 'interval' : settings?.p1_digest_times?.length ? 'scheduled' : 'interval')
  )
  const [p2Mode, setP2Mode] = useState<'interval' | 'scheduled'>(
    (settings?.p2_digest_interval_minutes ? 'interval' : settings?.p2_digest_times?.length ? 'scheduled' : 'interval')
  )

  // Alert cadence local state (for save button pattern)
  const [p0AlertsEnabled, setP0AlertsEnabled] = useState<boolean | null>(null)
  const [p1AlertsEnabled, setP1AlertsEnabled] = useState<boolean | null>(null)
  const [p2AlertsEnabled, setP2AlertsEnabled] = useState<boolean | null>(null)
  const [p3AlertsEnabled, setP3AlertsEnabled] = useState<boolean | null>(null)
  const [alertDedupWindow, setAlertDedupWindow] = useState<string | null>(null)
  const [p1Interval, setP1Interval] = useState<string | null>(null)
  const [p1ActiveHoursStart, setP1ActiveHoursStart] = useState<string | null>(null)
  const [p1ActiveHoursEnd, setP1ActiveHoursEnd] = useState<string | null>(null)
  const [p1OutsideHoursBehavior, setP1OutsideHoursBehavior] = useState<string | null>(null)
  const [p1Times, setP1Times] = useState<string[] | null>(null)
  const [p2Interval, setP2Interval] = useState<string | null>(null)
  const [p2ActiveHoursStart, setP2ActiveHoursStart] = useState<string | null>(null)
  const [p2ActiveHoursEnd, setP2ActiveHoursEnd] = useState<string | null>(null)
  const [p2OutsideHoursBehavior, setP2OutsideHoursBehavior] = useState<string | null>(null)
  const [p2Times, setP2Times] = useState<string[] | null>(null)
  const [p3Time, setP3Time] = useState<string | null>(null)

  // Update modes when settings change
  useEffect(() => {
    if (settings) {
      setP1Mode(settings.p1_digest_interval_minutes ? 'interval' : settings.p1_digest_times?.length ? 'scheduled' : 'interval')
      setP2Mode(settings.p2_digest_interval_minutes ? 'interval' : settings.p2_digest_times?.length ? 'scheduled' : 'interval')
    }
  }, [settings])

  // Update modes when settings change
  useEffect(() => {
    if (settings) {
      setP1Mode(settings.p1_digest_interval_minutes ? 'interval' : settings.p1_digest_times?.length ? 'scheduled' : 'interval')
      setP2Mode(settings.p2_digest_interval_minutes ? 'interval' : settings.p2_digest_times?.length ? 'scheduled' : 'interval')
    }
  }, [settings])

  const hasRulesChanges =
    customRules !== null && customRules !== (settings?.custom_classification_rules ?? '')
  const hasDefChanges =
    (p0Def !== null && p0Def !== (settings?.p0_definition ?? '')) ||
    (p1Def !== null && p1Def !== (settings?.p1_definition ?? '')) ||
    (p2Def !== null && p2Def !== (settings?.p2_definition ?? '')) ||
    (p3Def !== null && p3Def !== (settings?.p3_definition ?? ''))
  const hasDigestChanges =
    digestInstr !== null && digestInstr !== (settings?.digest_instructions ?? '')
  const hasCadenceChanges =
    (p0AlertsEnabled !== null && p0AlertsEnabled !== (settings?.p0_alerts_enabled ?? true)) ||
    (p1AlertsEnabled !== null && p1AlertsEnabled !== (settings?.p1_alerts_enabled ?? true)) ||
    (p2AlertsEnabled !== null && p2AlertsEnabled !== (settings?.p2_alerts_enabled ?? true)) ||
    (p3AlertsEnabled !== null && p3AlertsEnabled !== (settings?.p3_alerts_enabled ?? true)) ||
    (alertDedupWindow !== null && alertDedupWindow !== String(settings?.alert_dedup_window_minutes ?? 30)) ||
    (p1Interval !== null && p1Interval !== (settings?.p1_digest_interval_minutes?.toString() ?? '')) ||
    (p1ActiveHoursStart !== null && p1ActiveHoursStart !== (settings?.p1_digest_active_hours_start ?? '09:00')) ||
    (p1ActiveHoursEnd !== null && p1ActiveHoursEnd !== (settings?.p1_digest_active_hours_end ?? '18:00')) ||
    (p1OutsideHoursBehavior !== null && p1OutsideHoursBehavior !== (settings?.p1_digest_outside_hours_behavior ?? 'skip')) ||
    (p1Times !== null && JSON.stringify(p1Times) !== JSON.stringify(settings?.p1_digest_times ?? [])) ||
    (p2Interval !== null && p2Interval !== (settings?.p2_digest_interval_minutes?.toString() ?? '')) ||
    (p2ActiveHoursStart !== null && p2ActiveHoursStart !== (settings?.p2_digest_active_hours_start ?? '09:00')) ||
    (p2ActiveHoursEnd !== null && p2ActiveHoursEnd !== (settings?.p2_digest_active_hours_end ?? '18:00')) ||
    (p2OutsideHoursBehavior !== null && p2OutsideHoursBehavior !== (settings?.p2_digest_outside_hours_behavior ?? 'skip')) ||
    (p2Times !== null && JSON.stringify(p2Times) !== JSON.stringify(settings?.p2_digest_times ?? [])) ||
    (p3Time !== null && p3Time !== (settings?.p3_digest_time ?? '17:00'))

  const channels = channelData?.channels ?? []
  const visibleChannels = useMemo(() => {
    const filtered = showHiddenChannels ? channels : channels.filter((c) => !c.is_hidden)
    return [...filtered].sort((a, b) => a.channel_name.localeCompare(b.channel_name))
  }, [channels, showHiddenChannels])
  const hiddenCount = channels.filter((c) => c.is_hidden).length

  if (settingsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto">
    <div className="container max-w-3xl mx-auto py-6 space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold">Triage Settings</h1>
          <p className="text-sm text-muted-foreground">
            Configure how Slack messages are classified during focus mode
          </p>
        </div>
      </div>

      {/* General Settings */}
      <Card>
        <CardHeader>
          <CardTitle>General</CardTitle>
          <CardDescription>
            Control when triage is active and how sensitive classification should be
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label>Always-On Mode</Label>
              <p className="text-sm text-muted-foreground">
                Classify messages even when not in focus mode
              </p>
            </div>
            <Switch
              checked={settings?.is_always_on ?? false}
              onCheckedChange={(checked) =>
                updateSettings.mutate({ is_always_on: checked })
              }
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label>Sensitivity</Label>
              <p className="text-sm text-muted-foreground">
                Higher = more messages classified as P0/P1
              </p>
            </div>
            <Select
              value={settings?.sensitivity ?? 'medium'}
              onValueChange={(val) =>
                updateSettings.mutate({ sensitivity: val as 'low' | 'medium' | 'high' })
              }
            >
              <SelectTrigger className="w-32" disabled={!settings?.is_always_on}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Low</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="high">High</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label>Debug Mode</Label>
              <p className="text-sm text-muted-foreground">
                Show classification reasoning in notifications
              </p>
            </div>
            <Switch
              checked={settings?.debug_mode ?? false}
              onCheckedChange={(checked) =>
                updateSettings.mutate({ debug_mode: checked })
              }
            />
          </div>
        </CardContent>
      </Card>

      {/* Priority Definitions */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Priority Definitions</CardTitle>
              <CardDescription>
                Customize what each priority level means for your workflow
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setWizardOpen(true)}
            >
              <Sparkles className="h-3.5 w-3.5 mr-1.5" />
              Generate with AI
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="text-sm font-medium">P0 — Urgent (immediate notification)</Label>
            <Textarea
              rows={2}
              className="mt-1"
              placeholder={DEFAULT_P0}
              value={p0Def ?? settings?.p0_definition ?? ''}
              onChange={(e) => setP0Def(e.target.value)}
            />
          </div>
          <div>
            <Label className="text-sm font-medium">P1 — Important (digest at break)</Label>
            <Textarea
              rows={2}
              className="mt-1"
              placeholder={DEFAULT_P1}
              value={p1Def ?? settings?.p1_definition ?? ''}
              onChange={(e) => setP1Def(e.target.value)}
            />
          </div>
          <div>
            <Label className="text-sm font-medium">P2 — Notable (session digest)</Label>
            <Textarea
              rows={2}
              className="mt-1"
              placeholder={DEFAULT_P2}
              value={p2Def ?? settings?.p2_definition ?? ''}
              onChange={(e) => setP2Def(e.target.value)}
            />
          </div>
          <div>
            <Label className="text-sm font-medium">P3 — Low priority</Label>
            <Textarea
              rows={2}
              className="mt-1"
              placeholder={DEFAULT_P3}
              value={p3Def ?? settings?.p3_definition ?? ''}
              onChange={(e) => setP3Def(e.target.value)}
            />
          </div>
          {hasDefChanges && (
            <Button
              size="sm"
              disabled={updateSettings.isPending}
              onClick={() => {
                const payload: Record<string, string | null> = {}
                if (p0Def !== null) payload.p0_definition = p0Def || null
                if (p1Def !== null) payload.p1_definition = p1Def || null
                if (p2Def !== null) payload.p2_definition = p2Def || null
                if (p3Def !== null) payload.p3_definition = p3Def || null
                updateSettings.mutate(
                  payload,
                  {
                    onSuccess: () => {
                      setP0Def(null)
                      setP1Def(null)
                      setP2Def(null)
                      setP3Def(null)
                    },
                  }
                )
              }}
            >
              {updateSettings.isPending ? 'Saving...' : 'Save Definitions'}
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Classification Rules */}
      <Card>
        <CardHeader>
          <CardTitle>Additional Classification Rules</CardTitle>
          <CardDescription>
            Add custom rules to guide how messages are classified. These are injected into the AI classifier prompt.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            rows={4}
            placeholder={`e.g. Requests to borrow items are never P0\nMessages from #random are always P3`}
            value={customRules ?? settings?.custom_classification_rules ?? ''}
            onChange={(e) => setCustomRules(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Write natural-language rules, one per line. Max 2000 characters.
          </p>
          {hasRulesChanges && (
            <Button
              size="sm"
              disabled={updateSettings.isPending}
              onClick={() => {
                updateSettings.mutate(
                  { custom_classification_rules: customRules || null },
                  { onSuccess: () => setCustomRules(null) }
                )
              }}
            >
              {updateSettings.isPending ? 'Saving...' : 'Save Rules'}
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Digest Instructions */}
      <Card>
        <CardHeader>
          <CardTitle>Digest Instructions</CardTitle>
          <CardDescription>
            Tell the AI what to focus on when summarizing messages in your digest
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            rows={3}
            placeholder="e.g. Focus on action items and questions directed at me. Skip social messages."
            value={digestInstr ?? settings?.digest_instructions ?? ''}
            onChange={(e) => setDigestInstr(e.target.value)}
          />
          {hasDigestChanges && (
            <Button
              size="sm"
              disabled={updateSettings.isPending}
              onClick={() => {
                updateSettings.mutate(
                  { digest_instructions: digestInstr || null },
                  { onSuccess: () => setDigestInstr(null) }
                )
              }}
            >
              {updateSettings.isPending ? 'Saving...' : 'Save Instructions'}
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Alert Cadence Configuration */}
      <Card className={!settings?.is_always_on ? 'opacity-50' : ''}>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Alert Cadence</CardTitle>
              <CardDescription>
                Configure when you want to receive notifications and summaries for each priority level
              </CardDescription>
            </div>
            {!settings?.is_always_on && (
              <Badge variant="secondary">Requires Always-On Mode</Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {!settings?.is_always_on && (
            <div className="rounded-lg bg-muted p-3 text-sm">
              <p className="font-medium">Scheduled digests require Always-On Mode to be enabled.</p>
              <p className="text-muted-foreground mt-1">
                Priority definitions will still be used for post-focus digests even when Always-On is disabled.
              </p>
            </div>
          )}
          {/* P0 - Immediate Alerts */}
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-base">P0 — Urgent</Label>
              <p className="text-sm text-muted-foreground">Immediate notifications for urgent messages</p>
            </div>
            <Switch
              checked={p0AlertsEnabled ?? settings?.p0_alerts_enabled ?? true}
              onCheckedChange={(checked) => setP0AlertsEnabled(checked)}
              disabled={!settings?.is_always_on}
            />
          </div>

          {/* Alert Deduplication Window */}
          <div className="space-y-3">
            <Label>Alert Deduplication</Label>
            <div className="flex items-center gap-2">
              <Input
                type="number"
                min={1}
                max={120}
                value={alertDedupWindow ?? settings?.alert_dedup_window_minutes ?? 30}
                onChange={(e) => setAlertDedupWindow(e.target.value)}
                className="w-24"
                disabled={!settings?.is_always_on}
              />
              <span className="text-sm text-muted-foreground">
                Minutes between alerts for same thread/sender
              </span>
            </div>
          </div>

          {/* P1 Configuration */}
          <div className="space-y-3 border-t pt-4">
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-base">P1 — Important</Label>
                <p className="text-sm text-muted-foreground">Digest summaries at configured intervals/times</p>
              </div>
              <Switch
                checked={p1AlertsEnabled ?? settings?.p1_alerts_enabled ?? true}
                onCheckedChange={(checked) => setP1AlertsEnabled(checked)}
                disabled={!settings?.is_always_on}
              />
            </div>
            <RadioGroup
              value={p1Mode}
              onValueChange={(val) => {
                setP1Mode(val as 'interval' | 'scheduled')
                // Clear opposite mode's data when switching
                if (val === 'interval') {
                  updateSettings.mutate({ p1_digest_times: null })
                } else {
                  updateSettings.mutate({
                    p1_digest_interval_minutes: null,
                    p1_digest_active_hours_start: null,
                    p1_digest_active_hours_end: null,
                    p1_digest_outside_hours_behavior: null
                  })
                }
              }}
              disabled={!settings?.is_always_on}
            >
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="interval" id="p1-interval" />
                <Label htmlFor="p1-interval">Every X minutes during active hours</Label>
              </div>
              {p1Mode === 'interval' && (
                <div className="ml-6 space-y-3">
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      min={5}
                      max={180}
                      placeholder="30"
                      value={p1Interval ?? settings?.p1_digest_interval_minutes ?? ''}
                      onChange={(e) => setP1Interval(e.target.value)}
                      className="w-24"
                      disabled={!settings?.is_always_on}
                    />
                    <span className="text-sm text-muted-foreground">minutes</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Label className="text-sm">Active hours:</Label>
                    <Input
                      type="time"
                      value={p1ActiveHoursStart ?? settings?.p1_digest_active_hours_start ?? '09:00'}
                      onChange={(e) => setP1ActiveHoursStart(e.target.value)}
                      className="w-32"
                        disabled={!settings?.is_always_on}
                    />
                    <span className="text-sm">to</span>
                    <Input
                      type="time"
                      value={p1ActiveHoursEnd ?? settings?.p1_digest_active_hours_end ?? '18:00'}
                      onChange={(e) => setP1ActiveHoursEnd(e.target.value)}
                      className="w-32"
                        disabled={!settings?.is_always_on}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-sm">Outside active hours:</Label>
                    <RadioGroup
                      value={p1OutsideHoursBehavior ?? settings?.p1_digest_outside_hours_behavior ?? 'skip'}
                      onValueChange={(val) => setP1OutsideHoursBehavior(val)}
                      disabled={!settings?.is_always_on}
                    >
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="summary_next_window" id="p1-next-window" />
                        <Label htmlFor="p1-next-window" className="text-sm font-normal">
                          Summary at beginning of next window
                        </Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="skip" id="p1-skip" />
                        <Label htmlFor="p1-skip" className="text-sm font-normal">
                          Skip silently (wait for next interval)
                        </Label>
                      </div>
                    </RadioGroup>
                  </div>
                </div>
              )}
              <div className="flex items-center space-x-2 mt-3">
                <RadioGroupItem value="scheduled" id="p1-scheduled" />
                <Label htmlFor="p1-scheduled">At specific times of day</Label>
              </div>
              {p1Mode === 'scheduled' && (
                <div className="ml-6 space-y-2">
                  {(p1Times ?? settings?.p1_digest_times ?? []).map((time, idx) => (
                    <div key={idx} className="flex gap-2">
                      <Input
                        type="time"
                        value={time}
                        onChange={(e) => {
                          const newTimes = [...(p1Times ?? settings?.p1_digest_times ?? [])]
                          newTimes[idx] = e.target.value
                          setP1Times(newTimes)
                        }}
                        className="w-32"
                        disabled={!settings?.is_always_on}
                      />
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          const newTimes = (p1Times ?? settings?.p1_digest_times ?? []).filter((_, i) => i !== idx)
                          setP1Times(newTimes.length > 0 ? newTimes : [])
                        }}
                        disabled={!settings?.is_always_on}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const currentTimes = p1Times ?? settings?.p1_digest_times ?? []
                      setP1Times([...currentTimes, '09:00'])
                    }}
                    disabled={!settings?.is_always_on}
                  >
                    <Plus className="h-4 w-4 mr-1" /> Add Time
                  </Button>
                </div>
              )}
            </RadioGroup>
          </div>

          {/* P2 Configuration - Similar to P1 */}
          <div className="space-y-3 border-t pt-4">
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-base">P2 — Notable</Label>
                <p className="text-sm text-muted-foreground">Digest summaries at configured intervals/times</p>
              </div>
              <Switch
                checked={p2AlertsEnabled ?? settings?.p2_alerts_enabled ?? true}
                onCheckedChange={(checked) => setP2AlertsEnabled(checked)}
                disabled={!settings?.is_always_on}
              />
            </div>
            <RadioGroup
              value={p2Mode}
              onValueChange={(val) => setP2Mode(val as 'interval' | 'scheduled')}
              disabled={!settings?.is_always_on}
            >
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="interval" id="p2-interval" />
                <Label htmlFor="p2-interval">Every X minutes during active hours</Label>
              </div>
              {p2Mode === 'interval' && (
                <div className="ml-6 space-y-3">
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      min={5}
                      max={360}
                      placeholder="60"
                      value={p2Interval ?? settings?.p2_digest_interval_minutes ?? ''}
                      onChange={(e) => setP2Interval(e.target.value)}
                      className="w-24"
                      disabled={!settings?.is_always_on}
                    />
                    <span className="text-sm text-muted-foreground">minutes</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Label className="text-sm">Active hours:</Label>
                    <Input
                      type="time"
                      value={p2ActiveHoursStart ?? settings?.p2_digest_active_hours_start ?? '09:00'}
                      onChange={(e) => setP2ActiveHoursStart(e.target.value)}
                      className="w-32"
                        disabled={!settings?.is_always_on}
                    />
                    <span className="text-sm">to</span>
                    <Input
                      type="time"
                      value={p2ActiveHoursEnd ?? settings?.p2_digest_active_hours_end ?? '18:00'}
                      onChange={(e) => setP2ActiveHoursEnd(e.target.value)}
                      className="w-32"
                        disabled={!settings?.is_always_on}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-sm">Outside active hours:</Label>
                    <RadioGroup
                      value={p2OutsideHoursBehavior ?? settings?.p2_digest_outside_hours_behavior ?? 'skip'}
                      onValueChange={(val) => setP2OutsideHoursBehavior(val)}
                      disabled={!settings?.is_always_on}
                    >
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="summary_next_window" id="p2-next-window" />
                        <Label htmlFor="p2-next-window" className="text-sm font-normal">
                          Summary at beginning of next window
                        </Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="skip" id="p2-skip" />
                        <Label htmlFor="p2-skip" className="text-sm font-normal">
                          Skip silently
                        </Label>
                      </div>
                    </RadioGroup>
                  </div>
                </div>
              )}
              <div className="flex items-center space-x-2 mt-3">
                <RadioGroupItem value="scheduled" id="p2-scheduled" />
                <Label htmlFor="p2-scheduled">At specific times of day</Label>
              </div>
              {p2Mode === 'scheduled' && (
                <div className="ml-6 space-y-2">
                  {(p2Times ?? settings?.p2_digest_times ?? []).map((time, idx) => (
                    <div key={idx} className="flex gap-2">
                      <Input
                        type="time"
                        value={time}
                        onChange={(e) => {
                          const newTimes = [...(p2Times ?? settings?.p2_digest_times ?? [])]
                          newTimes[idx] = e.target.value
                          setP2Times(newTimes)
                        }}
                        className="w-32"
                        disabled={!settings?.is_always_on}
                      />
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          const newTimes = (p2Times ?? settings?.p2_digest_times ?? []).filter((_, i) => i !== idx)
                          setP2Times(newTimes.length > 0 ? newTimes : [])
                        }}
                        disabled={!settings?.is_always_on}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const currentTimes = p2Times ?? settings?.p2_digest_times ?? []
                      setP2Times([...currentTimes, '12:00'])
                    }}
                    disabled={!settings?.is_always_on}
                  >
                    <Plus className="h-4 w-4 mr-1" /> Add Time
                  </Button>
                </div>
              )}
            </RadioGroup>
          </div>

          {/* P3 Daily Digest */}
          <div className="space-y-3 border-t pt-4">
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-base">P3 — Daily Digest</Label>
                <p className="text-sm text-muted-foreground">Daily summary at configured time</p>
              </div>
              <Switch
                checked={p3AlertsEnabled ?? settings?.p3_alerts_enabled ?? true}
                onCheckedChange={(checked) => setP3AlertsEnabled(checked)}
                disabled={!settings?.is_always_on}
              />
            </div>
            <div className="flex items-center gap-2">
              <Input
                type="time"
                value={p3Time ?? settings?.p3_digest_time ?? '17:00'}
                onChange={(e) => setP3Time(e.target.value)}
                className="w-32"
                disabled={!settings?.is_always_on}
              />
              <span className="text-sm text-muted-foreground">Daily digest time</span>
            </div>
          </div>

          {/* Save button for cadence changes */}
          {hasCadenceChanges && (
            <Button
              size="sm"
              disabled={updateSettings.isPending || !settings?.is_always_on}
              onClick={() => {
                const payload: Record<string, any> = {}

                if (p0AlertsEnabled !== null) payload.p0_alerts_enabled = p0AlertsEnabled
                if (p1AlertsEnabled !== null) payload.p1_alerts_enabled = p1AlertsEnabled
                if (p2AlertsEnabled !== null) payload.p2_alerts_enabled = p2AlertsEnabled
                if (p3AlertsEnabled !== null) payload.p3_alerts_enabled = p3AlertsEnabled

                if (alertDedupWindow !== null) {
                  const val = parseInt(alertDedupWindow, 10)
                  if (val >= 1 && val <= 120) payload.alert_dedup_window_minutes = val
                }

                if (p1Mode === 'interval') {
                  if (p1Interval !== null) {
                    const val = parseInt(p1Interval, 10)
                    if (val >= 5 && val <= 180) payload.p1_digest_interval_minutes = val
                  }
                  if (p1ActiveHoursStart !== null) payload.p1_digest_active_hours_start = p1ActiveHoursStart
                  if (p1ActiveHoursEnd !== null) payload.p1_digest_active_hours_end = p1ActiveHoursEnd
                  if (p1OutsideHoursBehavior !== null) payload.p1_digest_outside_hours_behavior = p1OutsideHoursBehavior
                  payload.p1_digest_times = null
                } else if (p1Mode === 'scheduled' && p1Times !== null) {
                  payload.p1_digest_times = p1Times.length > 0 ? p1Times : null
                  payload.p1_digest_interval_minutes = null
                  payload.p1_digest_active_hours_start = null
                  payload.p1_digest_active_hours_end = null
                  payload.p1_digest_outside_hours_behavior = null
                }

                if (p2Mode === 'interval') {
                  if (p2Interval !== null) {
                    const val = parseInt(p2Interval, 10)
                    if (val >= 5 && val <= 360) payload.p2_digest_interval_minutes = val
                  }
                  if (p2ActiveHoursStart !== null) payload.p2_digest_active_hours_start = p2ActiveHoursStart
                  if (p2ActiveHoursEnd !== null) payload.p2_digest_active_hours_end = p2ActiveHoursEnd
                  if (p2OutsideHoursBehavior !== null) payload.p2_digest_outside_hours_behavior = p2OutsideHoursBehavior
                  payload.p2_digest_times = null
                } else if (p2Mode === 'scheduled' && p2Times !== null) {
                  payload.p2_digest_times = p2Times.length > 0 ? p2Times : null
                  payload.p2_digest_interval_minutes = null
                  payload.p2_digest_active_hours_start = null
                  payload.p2_digest_active_hours_end = null
                  payload.p2_digest_outside_hours_behavior = null
                }

                if (p3Time !== null) payload.p3_digest_time = p3Time

                updateSettings.mutate(payload, {
                  onSuccess: () => {
                    setP0AlertsEnabled(null)
                    setP1AlertsEnabled(null)
                    setP2AlertsEnabled(null)
                    setP3AlertsEnabled(null)
                    setAlertDedupWindow(null)
                    setP1Interval(null)
                    setP1ActiveHoursStart(null)
                    setP1ActiveHoursEnd(null)
                    setP1OutsideHoursBehavior(null)
                    setP1Times(null)
                    setP2Interval(null)
                    setP2ActiveHoursStart(null)
                    setP2ActiveHoursEnd(null)
                    setP2OutsideHoursBehavior(null)
                    setP2Times(null)
                    setP3Time(null)
                  },
                })
              }}
            >
              {updateSettings.isPending ? 'Saving...' : 'Save Cadence Settings'}
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Monitored Channels */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Monitored Channels</CardTitle>
              <CardDescription>
                Your Slack channels are automatically monitored for important messages
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              {hiddenCount > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowHiddenChannels(!showHiddenChannels)}
                >
                  <Settings className="h-4 w-4 mr-1" />
                  {showHiddenChannels ? 'Hide Hidden' : `Show Hidden (${hiddenCount})`}
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => autoEnroll.mutate()}
                disabled={autoEnroll.isPending}
              >
                <RefreshCw className={`h-4 w-4 mr-1 ${autoEnroll.isPending ? 'animate-spin' : ''}`} />
                Sync Channels
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {channelsLoading ? (
            <div className="text-center py-4 text-muted-foreground">Loading channels...</div>
          ) : channels.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-muted-foreground mb-4">No channels monitored yet</p>
              <Button onClick={() => autoEnroll.mutate()} disabled={autoEnroll.isPending}>
                {autoEnroll.isPending ? 'Syncing...' : 'Sync All My Channels'}
              </Button>
            </div>
          ) : (
            <div className="border rounded-lg overflow-hidden">
              <table className="w-full">
                <thead className="bg-muted/50">
                  <tr>
                    <th className="text-left p-3 font-medium">Channel</th>
                    <th className="text-left p-3 font-medium">Enabled</th>
                    <th className="text-left p-3 font-medium">Priority</th>
                    <th className="text-right p-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {visibleChannels.map((channel) => (
                    <tr key={channel.id} className="hover:bg-muted/30">
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          {channel.channel_type === 'private' ? (
                            <Lock className="h-4 w-4 text-muted-foreground" />
                          ) : (
                            <Hash className="h-4 w-4 text-muted-foreground" />
                          )}
                          <span className="font-medium">{channel.channel_name}</span>
                          {channel.is_hidden && (
                            <Badge variant="outline" className="ml-2">Hidden</Badge>
                          )}
                        </div>
                      </td>
                      <td className="p-3">
                        <Switch
                          checked={channel.is_active}
                          onCheckedChange={(checked) =>
                            updateChannel.mutate({
                              id: channel.id,
                              data: { is_active: checked },
                            })
                          }
                          className={cn(
                            "data-[state=checked]:bg-green-500",
                            "data-[state=unchecked]:bg-red-400"
                          )}
                        />
                      </td>
                      <td className="p-3">
                        <Select
                          value={channel.priority}
                          onValueChange={(val) =>
                            updateChannel.mutate({
                              id: channel.id,
                              data: { priority: val as ChannelPriority },
                            })
                          }
                        >
                          <SelectTrigger className="w-28 h-8">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="low">Low</SelectItem>
                            <SelectItem value="medium">Medium</SelectItem>
                            <SelectItem value="high">High</SelectItem>
                            <SelectItem value="critical">Critical</SelectItem>
                          </SelectContent>
                        </Select>
                      </td>
                      <td className="p-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setConfigChannel(channel)
                              setConfigModalOpen(true)
                            }}
                          >
                            <Settings className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              updateChannel.mutate({
                                id: channel.id,
                                data: { is_hidden: !channel.is_hidden },
                              })
                            }
                          >
                            {channel.is_hidden ? 'Show' : 'Hide'}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Channel Configuration Modal */}
      <ChannelConfigModal
        channel={configChannel}
        open={configModalOpen}
        onOpenChange={(open) => {
          setConfigModalOpen(open)
          if (!open) setConfigChannel(null)
        }}
      />
    </div>

    {/* AI Wizard Modal */}
    <ClassifierWizardModal
      open={wizardOpen}
      onOpenChange={setWizardOpen}
      onApply={(defs) => {
        setP0Def(defs.p0_definition)
        setP1Def(defs.p1_definition)
        setP2Def(defs.p2_definition)
        setP3Def(defs.p3_definition)
        setWizardOpen(false)
        updateSettings.mutate(
          {
            p0_definition: defs.p0_definition || null,
            p1_definition: defs.p1_definition || null,
            p2_definition: defs.p2_definition || null,
            p3_definition: defs.p3_definition || null,
          },
          {
            onSuccess: () => {
              setP0Def(null)
              setP1Def(null)
              setP2Def(null)
              setP3Def(null)
            },
          }
        )
      }}
    />
    </div>
  )
}
