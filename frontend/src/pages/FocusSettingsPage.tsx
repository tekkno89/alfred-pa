import { useState, useEffect } from 'react'
import { Settings, Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { VipList } from '@/components/focus/VipList'
import { useFocusSettings, useUpdateFocusSettings } from '@/hooks/useFocusMode'

export function FocusSettingsPage() {
  const { data: settings, isLoading } = useFocusSettings()
  const updateMutation = useUpdateFocusSettings()

  const [defaultMessage, setDefaultMessage] = useState('')
  const [hasChanges, setHasChanges] = useState(false)

  // Load settings into form
  useEffect(() => {
    if (settings) {
      setDefaultMessage(settings.default_message || '')
    }
  }, [settings])

  // Track changes
  useEffect(() => {
    if (!settings) return
    const changed = defaultMessage !== (settings.default_message || '')
    setHasChanges(changed)
  }, [defaultMessage, settings])

  const handleSave = async () => {
    await updateMutation.mutateAsync({
      default_message: defaultMessage || null,
    })
    setHasChanges(false)
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
            {hasChanges && (
              <div className="flex justify-end">
                <Button onClick={handleSave} disabled={updateMutation.isPending}>
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
