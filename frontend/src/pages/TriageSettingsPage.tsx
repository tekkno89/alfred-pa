import { useState, useMemo, useEffect } from 'react'
import { ArrowLeft, Plus, Trash2, Hash, Lock, RefreshCw, ChevronsUpDown, Check, Sparkles } from 'lucide-react'
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
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { cn } from '@/lib/utils'
import {
  useTriageSettings,
  useUpdateTriageSettings,
  useMonitoredChannels,
  useAddMonitoredChannel,
  useRemoveMonitoredChannel,
  useUpdateMonitoredChannel,
  useAvailableSlackChannels,
  useRefreshSlackChannels,
  useKeywordRules,
  useAddKeywordRule,
  useRemoveKeywordRule,
  useSourceExclusions,
  useAddSourceExclusion,
  useRemoveSourceExclusion,
} from '@/hooks/useTriage'
import { useNotificationContext } from '@/components/notifications/NotificationProvider'
import { ClassifierWizardModal } from '@/components/triage/ClassifierWizardModal'
import type { MonitoredChannel, ChannelPriority } from '@/types'

function ChannelConfig({ channel }: { channel: MonitoredChannel }) {
  const { data: rules = [] } = useKeywordRules(channel.id)
  const { data: exclusions = [] } = useSourceExclusions(channel.id)
  const addRule = useAddKeywordRule()
  const removeRule = useRemoveKeywordRule()
  const addExclusion = useAddSourceExclusion()
  const removeExclusion = useRemoveSourceExclusion()
  const updateChannel = useUpdateMonitoredChannel()
  const removeChannel = useRemoveMonitoredChannel()

  const [newKeyword, setNewKeyword] = useState('')
  const [newExclusionId, setNewExclusionId] = useState('')

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {channel.channel_type === 'private' ? (
              <Lock className="h-4 w-4 text-muted-foreground" />
            ) : (
              <Hash className="h-4 w-4 text-muted-foreground" />
            )}
            <CardTitle className="text-base">{channel.channel_name}</CardTitle>
            <Badge variant={channel.is_active ? 'default' : 'secondary'}>
              {channel.is_active ? 'Active' : 'Paused'}
            </Badge>
          </div>
          <div className="flex items-center gap-2">
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
            <Switch
              checked={channel.is_active}
              onCheckedChange={(checked) =>
                updateChannel.mutate({
                  id: channel.id,
                  data: { is_active: checked },
                })
              }
            />
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => removeChannel.mutate(channel.id)}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Keyword Rules */}
        <div>
          <Label className="text-sm font-medium">Keyword Rules</Label>
          <div className="flex gap-2 mt-1">
            <Input
              placeholder="Add keyword..."
              value={newKeyword}
              onChange={(e) => setNewKeyword(e.target.value)}
              className="h-8"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && newKeyword.trim()) {
                  addRule.mutate({
                    channelId: channel.id,
                    data: {
                      keyword_pattern: newKeyword.trim(),
                      priority_override: 'p0',
                    },
                  })
                  setNewKeyword('')
                }
              }}
            />
            <Button
              size="sm"
              variant="outline"
              className="h-8"
              disabled={!newKeyword.trim()}
              onClick={() => {
                addRule.mutate({
                  channelId: channel.id,
                  data: {
                    keyword_pattern: newKeyword.trim(),
                    priority_override: 'p0',
                  },
                })
                setNewKeyword('')
              }}
            >
              <Plus className="h-3 w-3" />
            </Button>
          </div>
          {rules.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {rules.map((rule) => (
                <Badge key={rule.id} variant="outline" className="gap-1">
                  {rule.keyword_pattern}
                  <button
                    className="ml-1 hover:text-destructive"
                    onClick={() =>
                      removeRule.mutate({
                        channelId: channel.id,
                        ruleId: rule.id,
                      })
                    }
                  >
                    x
                  </button>
                </Badge>
              ))}
            </div>
          )}
        </div>

        {/* Source Exclusions */}
        <div>
          <Label className="text-sm font-medium">Bot/User Exclusions</Label>
          <div className="flex gap-2 mt-1">
            <Input
              placeholder="Slack user/bot ID to exclude..."
              value={newExclusionId}
              onChange={(e) => setNewExclusionId(e.target.value)}
              className="h-8"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && newExclusionId.trim()) {
                  addExclusion.mutate({
                    channelId: channel.id,
                    data: {
                      slack_entity_id: newExclusionId.trim(),
                      entity_type: 'bot',
                      action: 'exclude',
                    },
                  })
                  setNewExclusionId('')
                }
              }}
            />
            <Button
              size="sm"
              variant="outline"
              className="h-8"
              disabled={!newExclusionId.trim()}
              onClick={() => {
                addExclusion.mutate({
                  channelId: channel.id,
                  data: {
                    slack_entity_id: newExclusionId.trim(),
                    entity_type: 'bot',
                    action: 'exclude',
                  },
                })
                setNewExclusionId('')
              }}
            >
              <Plus className="h-3 w-3" />
            </Button>
          </div>
          {exclusions.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {exclusions.map((ex) => (
                <Badge key={ex.id} variant="outline" className="gap-1">
                  {ex.display_name || ex.slack_entity_id} ({ex.action})
                  <button
                    className="ml-1 hover:text-destructive"
                    onClick={() =>
                      removeExclusion.mutate({
                        channelId: channel.id,
                        exclusionId: ex.id,
                      })
                    }
                  >
                    x
                  </button>
                </Badge>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

const DEFAULT_P0 = 'Needs immediate attention RIGHT NOW. Production incidents, emergencies, someone explicitly saying something is urgent/critical.'
const DEFAULT_P1 = 'Time-sensitive requests that need action soon. Direct asks requiring a response, important questions needing input.'
const DEFAULT_P2 = 'Noteworthy but not time-sensitive. Project updates, FYI items, relevant discussions worth reviewing later.'
const DEFAULT_P3 = 'Low priority. General chatter, memes, social messages, automated notifications that need no action.'

export function TriageSettingsPage() {
  const navigate = useNavigate()
  const { data: settings, isLoading: settingsLoading } = useTriageSettings()
  const updateSettings = useUpdateTriageSettings()
  const { data: channelData, isLoading: channelsLoading } = useMonitoredChannels()
  const { data: slackChannels = [] } = useAvailableSlackChannels()
  const addChannel = useAddMonitoredChannel()
  const refreshChannels = useRefreshSlackChannels()

  // Wire SSE events to the refresh hook so it knows when the job finishes
  const { lastEvent } = useNotificationContext()
  useEffect(() => {
    if (lastEvent) {
      refreshChannels.onNotification(lastEvent)
    }
  }, [lastEvent]) // eslint-disable-line react-hooks/exhaustive-deps

  const [comboboxOpen, setComboboxOpen] = useState(false)
  const [selectedChannelId, setSelectedChannelId] = useState('')
  const [customRules, setCustomRules] = useState<string | null>(null)
  const [wizardOpen, setWizardOpen] = useState(false)

  // Priority definition local state
  const [p0Def, setP0Def] = useState<string | null>(null)
  const [p1Def, setP1Def] = useState<string | null>(null)
  const [p2Def, setP2Def] = useState<string | null>(null)
  const [p3Def, setP3Def] = useState<string | null>(null)
  const [digestInstr, setDigestInstr] = useState<string | null>(null)

  const hasRulesChanges =
    customRules !== null && customRules !== (settings?.custom_classification_rules ?? '')
  const hasDefChanges =
    (p0Def !== null && p0Def !== (settings?.p0_definition ?? '')) ||
    (p1Def !== null && p1Def !== (settings?.p1_definition ?? '')) ||
    (p2Def !== null && p2Def !== (settings?.p2_definition ?? '')) ||
    (p3Def !== null && p3Def !== (settings?.p3_definition ?? ''))
  const hasDigestChanges =
    digestInstr !== null && digestInstr !== (settings?.digest_instructions ?? '')

  const channels = channelData?.channels ?? []
  const availableToAdd = useMemo(() => {
    const monitoredIds = new Set(channels.map((c) => c.slack_channel_id))
    return slackChannels.filter((c) => !monitoredIds.has(c.id))
  }, [slackChannels, channels])

  const selectedChannel = slackChannels.find((c) => c.id === selectedChannelId)

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
              <SelectTrigger className="w-32">
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

      {/* Monitored Channels */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Monitored Channels</CardTitle>
              <CardDescription>
                Select Slack channels to monitor for important messages
              </CardDescription>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              disabled={refreshChannels.refreshing || refreshChannels.isPending}
              onClick={() => refreshChannels.mutate()}
              title="Refresh channel list from Slack"
            >
              <RefreshCw className={`h-4 w-4 ${refreshChannels.refreshing || refreshChannels.isPending ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2 mb-4">
            <Popover open={comboboxOpen} onOpenChange={setComboboxOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={comboboxOpen}
                  className="flex-1 justify-between font-normal"
                >
                  {selectedChannel
                    ? `${selectedChannel.is_private ? '🔒' : '#'} ${selectedChannel.name}`
                    : 'Search channels...'}
                  <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
                <Command>
                  <CommandInput placeholder="Type to search channels..." />
                  <CommandList>
                    <CommandEmpty>No channels found.</CommandEmpty>
                    <CommandGroup>
                      {availableToAdd.map((ch) => (
                        <CommandItem
                          key={ch.id}
                          value={ch.name}
                          onSelect={() => {
                            setSelectedChannelId(ch.id === selectedChannelId ? '' : ch.id)
                            setComboboxOpen(false)
                          }}
                        >
                          <Check
                            className={cn(
                              'mr-2 h-4 w-4',
                              selectedChannelId === ch.id ? 'opacity-100' : 'opacity-0'
                            )}
                          />
                          {ch.is_private ? '🔒' : '#'} {ch.name}
                          <span className="ml-auto text-xs text-muted-foreground">
                            {ch.num_members} members
                          </span>
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
            <Button
              disabled={!selectedChannelId || addChannel.isPending}
              onClick={() => {
                if (selectedChannel) {
                  addChannel.mutate({
                    slack_channel_id: selectedChannel.id,
                    channel_name: selectedChannel.name,
                    channel_type: selectedChannel.is_private ? 'private' : 'public',
                  })
                  setSelectedChannelId('')
                }
              }}
            >
              <Plus className="h-4 w-4 mr-1" /> Add
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Channel Configs */}
      {channelsLoading ? (
        <div className="text-center py-4 text-muted-foreground">Loading channels...</div>
      ) : channels.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          No channels monitored yet. Add a channel above to get started.
        </div>
      ) : (
        <div className="space-y-4">
          {channels.map((channel) => (
            <ChannelConfig key={channel.id} channel={channel} />
          ))}
        </div>
      )}
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
