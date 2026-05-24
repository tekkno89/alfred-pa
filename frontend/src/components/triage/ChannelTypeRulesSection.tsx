import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
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
  useMessageTypes,
  useChannelTypeRules,
  useCreateChannelTypeRule,
  useDeleteChannelTypeRule,
} from '@/hooks/useMessageTypes'
import type { MessageType, ChannelTypeRule } from '@/types'

interface ChannelTypeRulesSectionProps {
  channelId: string
}

const ACTION_LABELS: Record<string, { label: string; color: string }> = {
  notify_now: { label: 'Immediate', color: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200' },
  summarize_next: { label: 'Next Break', color: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200' },
  summarize_eod: { label: 'EOD', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200' },
  ignore: { label: 'Ignore', color: 'bg-gray-100 text-gray-800 dark:bg-gray-900/40 dark:text-gray-200' },
}

function AddRuleDialog({
  open,
  onOpenChange,
  channelId,
  messageTypes,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  channelId: string
  messageTypes: MessageType[]
}) {
  const [selectedTypeId, setSelectedTypeId] = useState('')
  const [selectedAction, setSelectedAction] = useState<'notify_now' | 'summarize_next' | 'summarize_eod' | 'ignore'>('summarize_next')

  const createRule = useCreateChannelTypeRule()

  const handleAdd = () => {
    if (!selectedTypeId) return

    createRule.mutate(
      {
        channelId,
        data: {
          message_type_id: selectedTypeId,
          action: selectedAction,
        },
      },
      {
        onSuccess: () => {
          setSelectedTypeId('')
          setSelectedAction('summarize_next')
          onOpenChange(false)
        },
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Type Rule</DialogTitle>
          <DialogDescription>
            Define how a specific message type should be handled in this channel.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>Message Type</Label>
            <Select value={selectedTypeId} onValueChange={setSelectedTypeId}>
              <SelectTrigger>
                <SelectValue placeholder="Select a message type..." />
              </SelectTrigger>
              <SelectContent>
                {messageTypes.map((type) => (
                  <SelectItem key={type.id} value={type.id}>
                    {type.type_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Action</Label>
            <Select value={selectedAction} onValueChange={(val) => setSelectedAction(val as typeof selectedAction)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="notify_now">Immediate - Notify right away</SelectItem>
                <SelectItem value="summarize_next">Next Break - Include in next break digest</SelectItem>
                <SelectItem value="summarize_eod">EOD - Include in end-of-day summary</SelectItem>
                <SelectItem value="ignore">Ignore - Don't include in any digest</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleAdd} disabled={!selectedTypeId || createRule.isPending}>
            {createRule.isPending ? 'Adding...' : 'Add Rule'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function ChannelTypeRulesSection({ channelId }: ChannelTypeRulesSectionProps) {
  const [dialogOpen, setDialogOpen] = useState(false)

  const { data: messageTypes } = useMessageTypes()
  const { data: rules, isLoading } = useChannelTypeRules(channelId)
  const deleteRule = useDeleteChannelTypeRule()

  if (isLoading) {
    return (
      <div className="text-sm text-muted-foreground py-4">
        Loading type rules...
      </div>
    )
  }

  const existingTypeIds = new Set(rules?.map((r) => r.message_type_id) ?? [])
  const availableTypes = messageTypes?.filter((t) => !existingTypeIds.has(t.id)) ?? []

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Label>Message Type Rules</Label>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setDialogOpen(true)}
          disabled={availableTypes.length === 0}
        >
          <Plus className="h-4 w-4 mr-1" />
          Add Rule
        </Button>
      </div>

      {rules && rules.length > 0 ? (
        <div className="border rounded-lg divide-y">
          {rules.map((rule) => (
            <RuleRow
              key={rule.id}
              rule={rule}
              onDelete={() => deleteRule.mutate({ channelId, ruleId: rule.id })}
            />
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground py-2">
          No type rules configured. Add rules to customize how specific message types are handled in this channel.
        </p>
      )}

      <AddRuleDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        channelId={channelId}
        messageTypes={availableTypes}
      />
    </div>
  )
}

function RuleRow({
  rule,
  onDelete,
}: {
  rule: ChannelTypeRule
  onDelete: () => void
}) {
  const actionInfo = ACTION_LABELS[rule.action] ?? { label: rule.action, color: '' }
  const typeName = rule.message_type?.type_name ?? 'Unknown Type'

  return (
    <div className="flex items-center justify-between p-3 hover:bg-muted/50">
      <div className="flex items-center gap-3">
        <span className="font-medium">{typeName}</span>
        <ArrowRight className="h-4 w-4 text-muted-foreground" />
        <Badge variant="outline" className={actionInfo.color}>
          {actionInfo.label}
        </Badge>
      </div>
      <Button variant="ghost" size="sm" onClick={onDelete} className="text-muted-foreground hover:text-destructive">
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  )
}

function ArrowRight({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </svg>
  )
}
