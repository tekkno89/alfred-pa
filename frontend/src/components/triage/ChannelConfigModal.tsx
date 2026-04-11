import { useState, useEffect } from 'react'
import { Settings, X, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import {
  useUpdateMonitoredChannel,
  useSourceExclusions,
  useAddSourceExclusion,
  useRemoveSourceExclusion,
  useChannelMembers,
} from '@/hooks/useTriage'
import type { MonitoredChannel, ChannelPriority, ChannelMember } from '@/types'

interface ChannelConfigModalProps {
  channel: MonitoredChannel | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ChannelConfigModal({ channel, open, onOpenChange }: ChannelConfigModalProps) {
  const [priority, setPriority] = useState<ChannelPriority>('medium')
  const [triageInstructions, setTriageInstructions] = useState('')
  const [hasChanges, setHasChanges] = useState(false)

  const updateChannel = useUpdateMonitoredChannel()
  const { data: exclusions = [] } = useSourceExclusions(channel?.id || '')
  const { data: members = [], isLoading: membersLoading } = useChannelMembers(
    channel ? channel.slack_channel_id : null
  )
  const addExclusion = useAddSourceExclusion()
  const removeExclusion = useRemoveSourceExclusion()

  // Load channel data when modal opens
  useEffect(() => {
    if (channel) {
      setPriority(channel.priority)
      setTriageInstructions(channel.triage_instructions || '')
      setHasChanges(false)
    }
  }, [channel])

  // Track changes
  useEffect(() => {
    if (channel) {
      const priorityChanged = priority !== channel.priority
      const instructionsChanged = triageInstructions !== (channel.triage_instructions || '')
      setHasChanges(priorityChanged || instructionsChanged)
    }
  }, [priority, triageInstructions, channel])

  const handleSave = async () => {
    if (!channel) return

    await updateChannel.mutateAsync({
      id: channel.id,
      data: {
        priority,
        triage_instructions: triageInstructions || null,
      },
    })
    setHasChanges(false)
    onOpenChange(false)
  }

  const handleAddExclusion = async (member: ChannelMember) => {
    if (!channel) return

    await addExclusion.mutateAsync({
      channelId: channel.id,
      data: {
        slack_entity_id: member.slack_user_id,
        entity_type: member.is_bot ? 'bot' : 'user',
        action: 'exclude',
        display_name: member.display_name,
      },
    })
  }

  const handleRemoveExclusion = async (exclusionId: string) => {
    if (!channel) return

    await removeExclusion.mutateAsync({
      channelId: channel.id,
      exclusionId,
    })
  }

  if (!channel) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {channel.channel_type === 'private' ? '🔒' : '#'} {channel.channel_name} - Configuration
          </DialogTitle>
          <DialogDescription>
            Configure priority, triage instructions, and exclusions for this channel
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Priority */}
          <div className="space-y-2">
            <Label htmlFor="priority">Priority</Label>
            <Select value={priority} onValueChange={(val) => setPriority(val as ChannelPriority)}>
              <SelectTrigger id="priority">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Low</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="high">High</SelectItem>
                <SelectItem value="critical">Critical</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Triage Instructions */}
          <div className="space-y-2">
            <Label htmlFor="instructions">Triage Instructions</Label>
            <Textarea
              id="instructions"
              placeholder="e.g., Ignore GitHub bot messages unless they mention incidents. Prioritize customer support questions."
              value={triageInstructions}
              onChange={(e) => setTriageInstructions(e.target.value)}
              rows={4}
              maxLength={2000}
            />
            <p className="text-xs text-muted-foreground">
              Natural language guidance for the AI when triaging messages in this channel
            </p>
          </div>

          {/* Exclusions */}
          <div className="space-y-3">
            <Label>Exclude from Monitoring</Label>

            {/* Current exclusions */}
            {exclusions.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {exclusions.map((ex) => (
                  <Badge key={ex.id} variant="outline" className="gap-1">
                    {ex.display_name || ex.slack_entity_id}
                    <button
                      className="ml-1 hover:text-destructive"
                      onClick={() => handleRemoveExclusion(ex.id)}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}

            {/* Add exclusion dropdown */}
            <div className="space-y-2">
              <Select onValueChange={(value) => {
                const member = members.find((m) => m.slack_user_id === value)
                if (member) {
                  handleAddExclusion(member)
                }
              }}>
                <SelectTrigger>
                  <SelectValue placeholder="Search channel members..." />
                </SelectTrigger>
                <SelectContent>
                  {membersLoading ? (
                    <div className="flex items-center justify-center py-4">
                      <Loader2 className="h-4 w-4 animate-spin" />
                    </div>
                  ) : (
                    <>
                      {/* Group: Bots & Apps */}
                      {members.filter((m) => m.is_bot || m.is_app).length > 0 && (
                        <div className="px-2 py-1.5 text-sm font-semibold text-muted-foreground">
                          Bots & Apps
                        </div>
                      )}
                      {members
                        .filter((m) => m.is_bot || m.is_app)
                        .map((member) => (
                          <SelectItem
                            key={member.slack_user_id}
                            value={member.slack_user_id}
                            disabled={exclusions.some((ex) => ex.slack_entity_id === member.slack_user_id)}
                          >
                            {member.display_name}
                          </SelectItem>
                        ))}

                      {/* Group: Users */}
                      {members.filter((m) => !m.is_bot && !m.is_app).length > 0 && (
                        <div className="px-2 py-1.5 text-sm font-semibold text-muted-foreground mt-2">
                          Users
                        </div>
                      )}
                      {members
                        .filter((m) => !m.is_bot && !m.is_app)
                        .map((member) => (
                          <SelectItem
                            key={member.slack_user_id}
                            value={member.slack_user_id}
                            disabled={exclusions.some((ex) => ex.slack_entity_id === member.slack_user_id)}
                          >
                            {member.display_name}
                          </SelectItem>
                        ))}
                    </>
                  )}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Select users, bots, or apps to exclude from triage
              </p>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!hasChanges || updateChannel.isPending}>
            {updateChannel.isPending ? 'Saving...' : 'Save Changes'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}