import { useNavigate } from 'react-router-dom'
import { Settings } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useCalendars, useUpdateCalendarPreferences } from '@/hooks/useCalendar'
import type { CalendarInfo, CalendarPreferenceItem } from '@/types'

const COLOR_OPTIONS = [
  '#4285f4', '#0b8043', '#8e24aa', '#d50000', '#f4511e',
  '#f6bf26', '#039be5', '#616161', '#33b679', '#e67c73',
]

interface CalendarSidebarProps {
  collapsed: boolean
}

export function CalendarSidebar({ collapsed }: CalendarSidebarProps) {
  const navigate = useNavigate()
  const { data } = useCalendars()
  const updatePrefs = useUpdateCalendarPreferences()
  const calendars = data?.calendars ?? []

  if (collapsed) return null

  // Group by account
  const accounts = new Map<string, CalendarInfo[]>()
  for (const cal of calendars) {
    const key = cal.account_email || cal.account_label
    if (!accounts.has(key)) accounts.set(key, [])
    accounts.get(key)!.push(cal)
  }

  const handleToggle = (cal: CalendarInfo) => {
    const updated: CalendarPreferenceItem[] = calendars.map((c) => ({
      account_label: c.account_label,
      calendar_id: c.id,
      calendar_name: c.name,
      color: c.color,
      visible: c.id === cal.id && c.account_label === cal.account_label ? !c.visible : c.visible,
    }))
    updatePrefs.mutate(updated)
  }

  const handleColorChange = (cal: CalendarInfo, newColor: string) => {
    const updated: CalendarPreferenceItem[] = calendars.map((c) => ({
      account_label: c.account_label,
      calendar_id: c.id,
      calendar_name: c.name,
      color: c.id === cal.id && c.account_label === cal.account_label ? newColor : c.color,
      visible: c.visible,
    }))
    updatePrefs.mutate(updated)
  }

  return (
    <div className="w-56 border-l shrink-0 p-3 overflow-y-auto">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium">Calendars</h3>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => navigate('/settings/integrations')}
          title="Manage accounts"
        >
          <Settings className="h-3.5 w-3.5" />
        </Button>
      </div>

      {calendars.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No calendars connected.{' '}
          <button
            className="underline hover:text-foreground"
            onClick={() => navigate('/settings/integrations')}
          >
            Add account
          </button>
        </p>
      ) : (
        <div className="space-y-4">
          {Array.from(accounts.entries()).map(([accountKey, cals]) => (
            <div key={accountKey}>
              <p className="text-xs text-muted-foreground mb-1 truncate" title={accountKey}>
                {accountKey}
              </p>
              <div className="space-y-1">
                {cals.map((cal) => (
                  <div key={`${cal.account_label}-${cal.id}`} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={cal.visible}
                      onChange={() => handleToggle(cal)}
                      className="h-3.5 w-3.5 rounded cursor-pointer"
                      style={{ accentColor: cal.color }}
                    />
                    <Popover>
                      <PopoverTrigger asChild>
                        <button
                          className="h-3 w-3 rounded-full shrink-0 cursor-pointer hover:ring-2 ring-offset-1 ring-muted-foreground/30"
                          style={{ backgroundColor: cal.color }}
                        />
                      </PopoverTrigger>
                      <PopoverContent className="w-auto p-2" align="start">
                        <div className="grid grid-cols-5 gap-1">
                          {COLOR_OPTIONS.map((color) => (
                            <button
                              key={color}
                              className={`h-6 w-6 rounded-full cursor-pointer hover:ring-2 ring-offset-1 ring-muted-foreground/50 ${
                                color === cal.color ? 'ring-2 ring-primary' : ''
                              }`}
                              style={{ backgroundColor: color }}
                              onClick={() => handleColorChange(cal, color)}
                            />
                          ))}
                        </div>
                      </PopoverContent>
                    </Popover>
                    <span className="text-xs truncate flex-1" title={cal.name}>
                      {cal.name}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
