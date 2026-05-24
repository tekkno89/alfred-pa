import { useState, useEffect } from 'react'
import { Clock, Sun, Moon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
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
import { useActiveHours, useUpdateActiveHours, useUpdateBreakthrough } from '@/hooks/useActiveHours'
import { useTriageSettings } from '@/hooks/useTriage'
import type { ActiveHoursConfig } from '@/types'

const DAYS = [
  { value: 0, label: 'Monday', short: 'Mon' },
  { value: 1, label: 'Tuesday', short: 'Tue' },
  { value: 2, label: 'Wednesday', short: 'Wed' },
  { value: 3, label: 'Thursday', short: 'Thu' },
  { value: 4, label: 'Friday', short: 'Fri' },
  { value: 5, label: 'Saturday', short: 'Sat' },
  { value: 6, label: 'Sunday', short: 'Sun' },
]

const TIME_OPTIONS = Array.from({ length: 48 }, (_, i) => {
  const hours = Math.floor(i / 2)
  const minutes = i % 2 === 0 ? '00' : '30'
  return `${hours.toString().padStart(2, '0')}:${minutes}`
})

function getDefaultConfig(): ActiveHoursConfig[] {
  return DAYS.map((day) => ({
    id: `default-${day.value}`,
    user_id: '',
    day_of_week: day.value,
    start_time: '09:00',
    end_time: '17:00',
    is_enabled: day.value < 5,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }))
}

export function ActiveHoursCard() {
  const { data: settings } = useTriageSettings()
  const { data: existingConfigs, isLoading } = useActiveHours()
  const updateActiveHours = useUpdateActiveHours()
  const updateBreakthrough = useUpdateBreakthrough()

  const [configs, setConfigs] = useState<ActiveHoursConfig[]>([])
  const [hasChanges, setHasChanges] = useState(false)

  useEffect(() => {
    if (existingConfigs && existingConfigs.length > 0) {
      setConfigs(existingConfigs)
    } else if (existingConfigs) {
      setConfigs(getDefaultConfig())
    }
  }, [existingConfigs])

  useEffect(() => {
    if (existingConfigs && existingConfigs.length > 0) {
      const changed = JSON.stringify(configs) !== JSON.stringify(existingConfigs)
      setHasChanges(changed)
    }
  }, [configs, existingConfigs])

  const handleTimeChange = (dayOfWeek: number, field: 'start_time' | 'end_time', value: string) => {
    setConfigs((prev) =>
      prev.map((c) =>
        c.day_of_week === dayOfWeek ? { ...c, [field]: value } : c
      )
    )
  }

  const handleToggle = (dayOfWeek: number, enabled: boolean) => {
    setConfigs((prev) =>
      prev.map((c) =>
        c.day_of_week === dayOfWeek ? { ...c, is_enabled: enabled } : c
      )
    )
  }

  const handlePreset = (preset: '9-5' | '24/7') => {
    const newConfigs = DAYS.map((day) => ({
      ...configs.find((c) => c.day_of_week === day.value)!,
      start_time: preset === '24/7' ? '00:00' : '09:00',
      end_time: preset === '24/7' ? '23:30' : '17:00',
      is_enabled: preset === '24/7' || day.value < 5,
    }))
    setConfigs(newConfigs)
  }

  const handleSave = () => {
    updateActiveHours.mutate({
      configs: configs.map((c) => ({
        day_of_week: c.day_of_week,
        start_time: c.start_time,
        end_time: c.end_time,
        is_enabled: c.is_enabled,
      })),
    })
  }

  const breakthrough = settings?.active_hours_breakthrough ?? 'allow_notify_now'

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          Loading active hours...
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Active Hours
            </CardTitle>
            <CardDescription>
              Set when you're typically available. Messages outside these hours follow breakthrough rules.
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => handlePreset('9-5')}>
              <Sun className="h-4 w-4 mr-1" />
              9-5 M-F
            </Button>
            <Button variant="outline" size="sm" onClick={() => handlePreset('24/7')}>
              <Moon className="h-4 w-4 mr-1" />
              24/7
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid grid-cols-7 gap-2">
          {DAYS.map((day) => {
            const config = configs.find((c) => c.day_of_week === day.value)
            if (!config) return null

            return (
              <div
                key={day.value}
                className={`p-3 rounded-lg border ${
                  config.is_enabled ? 'bg-background' : 'bg-muted/50'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <Label className="text-sm font-medium">{day.short}</Label>
                  <Switch
                    checked={config.is_enabled}
                    onCheckedChange={(checked) => handleToggle(day.value, checked)}
                    className="scale-75"
                  />
                </div>
                {config.is_enabled && (
                  <div className="space-y-1">
                    <Select
                      value={config.start_time}
                      onValueChange={(val) => handleTimeChange(day.value, 'start_time', val)}
                    >
                      <SelectTrigger className="h-7 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {TIME_OPTIONS.map((time) => (
                          <SelectItem key={time} value={time} className="text-xs">
                            {time}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <div className="text-xs text-center text-muted-foreground">to</div>
                    <Select
                      value={config.end_time}
                      onValueChange={(val) => handleTimeChange(day.value, 'end_time', val)}
                    >
                      <SelectTrigger className="h-7 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {TIME_OPTIONS.map((time) => (
                          <SelectItem key={time} value={time} className="text-xs">
                            {time}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {hasChanges && (
          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={handleSave}
              disabled={updateActiveHours.isPending}
            >
              {updateActiveHours.isPending ? 'Saving...' : 'Save Hours'}
            </Button>
          </div>
        )}

        <div className="border-t pt-4">
          <Label className="text-sm font-medium">Breakthrough Behavior</Label>
          <p className="text-sm text-muted-foreground mb-3">
            What happens to urgent (P0) messages outside your active hours?
          </p>
          <RadioGroup
            value={breakthrough}
            onValueChange={(val) =>
              updateBreakthrough.mutate(val as 'allow_notify_now' | 'queue_all')
            }
          >
            <div className="flex items-start space-x-3 space-y-0">
              <RadioGroupItem value="allow_notify_now" id="allow_notify_now" />
              <div className="grid gap-1.5 leading-none">
                <Label htmlFor="allow_notify_now" className="font-medium">
                  Allow urgent notifications
                </Label>
                <p className="text-xs text-muted-foreground">
                  P0 messages will notify immediately even outside active hours
                </p>
              </div>
            </div>
            <div className="flex items-start space-x-3 space-y-0 mt-2">
              <RadioGroupItem value="queue_all" id="queue_all" />
              <div className="grid gap-1.5 leading-none">
                <Label htmlFor="queue_all" className="font-medium">
                  Queue everything
                </Label>
                <p className="text-xs text-muted-foreground">
                  All messages are queued until your next active period
                </p>
              </div>
            </div>
          </RadioGroup>
        </div>
      </CardContent>
    </Card>
  )
}
