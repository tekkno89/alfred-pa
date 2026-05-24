import { useState, useMemo, useEffect } from 'react'
import { ArrowLeft, Hash, Lock, RefreshCw, Sparkles, Settings, Clock } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
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
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import {
  useTriageSettings,
  useUpdateTriageSettings,
  useMonitoredChannels,
  useUpdateMonitoredChannel,
  useRefreshSlackChannels,
  useAutoEnrollChannels,
} from '@/hooks/useTriage'
import { useCreateMessageType } from '@/hooks/useMessageTypes'
import { useNotificationContext } from '@/components/notifications/NotificationProvider'
import { ClassifierWizardModal } from '@/components/triage/ClassifierWizardModal'
import { ChannelConfigModal } from '@/components/triage/ChannelConfigModal'
import { AwayModeToggle } from '@/components/triage/AwayModeToggle'
import { AdaptiveWindowsCard } from '@/components/triage/AdaptiveWindowsCard'
import { ActiveHoursCard } from '@/components/triage/ActiveHoursCard'
import { MessageTypesCard } from '@/components/triage/MessageTypesCard'
import { LearnedKeywordsCard } from '@/components/triage/LearnedKeywordsCard'
import { SenderPatternsCard } from '@/components/triage/SenderPatternsCard'
import { RecentCorrectionsCard } from '@/components/triage/RecentCorrectionsCard'
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

  // Message types
  const createMessageType = useCreateMessageType()

  // Priority definition local state
  const [p0Def, setP0Def] = useState<string | null>(null)
  const [p1Def, setP1Def] = useState<string | null>(null)
  const [p2Def, setP2Def] = useState<string | null>(null)
  const [p3Def, setP3Def] = useState<string | null>(null)

  const hasRulesChanges =
    customRules !== null && customRules !== (settings?.custom_classification_rules ?? '')
  const hasDefChanges =
    (p0Def !== null && p0Def !== (settings?.p0_definition ?? '')) ||
    (p1Def !== null && p1Def !== (settings?.p1_definition ?? '')) ||
    (p2Def !== null && p2Def !== (settings?.p2_definition ?? '')) ||
    (p3Def !== null && p3Def !== (settings?.p3_definition ?? ''))

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

          <div className="flex items-center justify-between">
            <div>
              <Label className="flex items-center gap-2">
                <Clock className="h-4 w-4" />
                EOD Review Time
              </Label>
              <p className="text-sm text-muted-foreground">
                Time for end-of-day digest summary
              </p>
            </div>
            <Input
              type="time"
              className="w-32"
              value={settings?.eod_review_time ?? '17:00'}
              onChange={(e) =>
                updateSettings.mutate({ eod_review_time: e.target.value })
              }
            />
          </div>

          <div className="border-t pt-4">
            <AwayModeToggle />
          </div>
        </CardContent>
      </Card>

      {/* Active Hours */}
      <ActiveHoursCard />

      {/* Adaptive Delivery Windows */}
      <AdaptiveWindowsCard />

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
            <Label className="text-sm font-medium">P0 - Immediate (notify_now)</Label>
            <Textarea
              rows={2}
              className="mt-1"
              placeholder={DEFAULT_P0}
              value={p0Def ?? settings?.p0_definition ?? ''}
              onChange={(e) => setP0Def(e.target.value)}
            />
          </div>
          <div>
            <Label className="text-sm font-medium">P1 - Soon (summarize_next)</Label>
            <Textarea
              rows={2}
              className="mt-1"
              placeholder={DEFAULT_P1}
              value={p1Def ?? settings?.p1_definition ?? ''}
              onChange={(e) => setP1Def(e.target.value)}
            />
          </div>
          <div>
            <Label className="text-sm font-medium">P2 - Later (summarize_eod)</Label>
            <Textarea
              rows={2}
              className="mt-1"
              placeholder={DEFAULT_P2}
              value={p2Def ?? settings?.p2_definition ?? ''}
              onChange={(e) => setP2Def(e.target.value)}
            />
          </div>
          <div>
            <Label className="text-sm font-medium">P3 - Ignore</Label>
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

      {/* Message Types */}
      <MessageTypesCard />

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
                    <th className="text-left p-3 font-medium">Summary</th>
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
                       <td className="p-3">
                         <Select
                           value={channel.summary_behavior}
                           onValueChange={(val) =>
                             updateChannel.mutate({
                               id: channel.id,
                               data: { summary_behavior: val as 'default' | 'initial_only' },
                             })
                           }
                         >
                           <SelectTrigger className="w-36 h-8">
                             <SelectValue />
                           </SelectTrigger>
                           <SelectContent>
                             <SelectItem value="default">
                               <div>
                                 <div className="font-medium">Default</div>
                                 <div className="text-xs text-muted-foreground">Include all messages and replies</div>
                               </div>
                             </SelectItem>
                             <SelectItem value="initial_only">
                               <div>
                                 <div className="font-medium">Initial Only</div>
                                 <div className="text-xs text-muted-foreground">Exclude thread replies from summaries</div>
                               </div>
                             </SelectItem>
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

      {/* Transparency Section */}
      <div className="space-y-6">
        <h2 className="text-lg font-semibold">Transparency</h2>
        <p className="text-sm text-muted-foreground">
          View the data Alfred has learned from your feedback. This influences how messages are classified.
        </p>
        <LearnedKeywordsCard />
        <SenderPatternsCard />
        <RecentCorrectionsCard />
      </div>

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
      onApply={(defs, messageTypes) => {
        setP0Def(defs.p0_definition)
        setP1Def(defs.p1_definition)
        setP2Def(defs.p2_definition)
        setP3Def(defs.p3_definition)
        setWizardOpen(false)
        
        // Save priority definitions
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
        
        // Save message types
        messageTypes.forEach((type) => {
          createMessageType.mutate({
            type_name: type.type_name,
            type_definition: type.type_definition,
          })
        })
      }}
    />
    </div>
  )
}
