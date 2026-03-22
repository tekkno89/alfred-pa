import { useState, useMemo } from 'react'
import { ArrowLeft, Plus, Trash2, Hash, Lock, RefreshCw } from 'lucide-react'
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
                      urgency_override: 'urgent',
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
                    urgency_override: 'urgent',
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

export function TriageSettingsPage() {
  const navigate = useNavigate()
  const { data: settings, isLoading: settingsLoading } = useTriageSettings()
  const updateSettings = useUpdateTriageSettings()
  const { data: channelData, isLoading: channelsLoading } = useMonitoredChannels()
  const { data: slackChannels = [] } = useAvailableSlackChannels()
  const addChannel = useAddMonitoredChannel()
  const refreshChannels = useRefreshSlackChannels()

  const [selectedChannelId, setSelectedChannelId] = useState('')
  const [channelSearch, setChannelSearch] = useState('')
  const [customRules, setCustomRules] = useState<string | null>(null)
  const hasRulesChanges =
    customRules !== null && customRules !== (settings?.custom_classification_rules ?? '')

  if (settingsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    )
  }

  const channels = channelData?.channels ?? []
  const availableToAdd = useMemo(() => {
    const monitoredIds = new Set(channels.map((c) => c.slack_channel_id))
    const notMonitored = slackChannels.filter((c) => !monitoredIds.has(c.id))
    if (!channelSearch.trim()) return notMonitored
    const q = channelSearch.toLowerCase()
    return notMonitored.filter((c) => c.name.toLowerCase().includes(q))
  }, [slackChannels, channels, channelSearch])

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
                Higher = more messages classified as urgent
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

      {/* Classification Rules */}
      <Card>
        <CardHeader>
          <CardTitle>Classification Rules</CardTitle>
          <CardDescription>
            Add custom rules to guide how messages are classified. These are injected into the AI classifier prompt.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            rows={4}
            placeholder={`e.g. Requests to borrow items are never urgent\nMessages from #random are always digest`}
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
              disabled={refreshChannels.isPending}
              onClick={() => refreshChannels.mutate()}
              title="Refresh channel list from Slack"
            >
              <RefreshCw className={`h-4 w-4 ${refreshChannels.isPending ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-2 mb-4">
            <Input
              placeholder="Search channels..."
              value={channelSearch}
              onChange={(e) => setChannelSearch(e.target.value)}
              className="h-8"
            />
            <div className="flex gap-2">
              <Select value={selectedChannelId} onValueChange={setSelectedChannelId}>
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder="Select a channel to add..." />
                </SelectTrigger>
                <SelectContent>
                  {availableToAdd.map((ch) => (
                    <SelectItem key={ch.id} value={ch.id}>
                      {ch.is_private ? '🔒' : '#'} {ch.name} ({ch.num_members} members)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                disabled={!selectedChannelId || addChannel.isPending}
                onClick={() => {
                  const ch = slackChannels.find((c) => c.id === selectedChannelId)
                  if (ch) {
                    addChannel.mutate({
                      slack_channel_id: ch.id,
                      channel_name: ch.name,
                      channel_type: ch.is_private ? 'private' : 'public',
                    })
                    setSelectedChannelId('')
                  }
                }}
              >
                <Plus className="h-4 w-4 mr-1" /> Add
              </Button>
            </div>
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
    </div>
  )
}
