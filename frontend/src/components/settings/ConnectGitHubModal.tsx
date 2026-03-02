import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { GitHubAppConfig } from '@/types'

interface ConnectGitHubModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (accountLabel: string, appConfigId?: string) => void
  appConfigs: GitHubAppConfig[]
  isLoading: boolean
}

const NO_APP_CONFIG = '__global__'

export function ConnectGitHubModal({
  open,
  onOpenChange,
  onSubmit,
  appConfigs,
  isLoading,
}: ConnectGitHubModalProps) {
  const [accountLabel, setAccountLabel] = useState('')
  const [selectedConfigId, setSelectedConfigId] = useState<string>(NO_APP_CONFIG)

  // Pre-fill account label when config selection changes
  const handleConfigChange = (value: string) => {
    setSelectedConfigId(value)
    if (value !== NO_APP_CONFIG) {
      const config = appConfigs.find((c) => c.id === value)
      if (config) {
        setAccountLabel(config.label.toLowerCase())
      }
    }
  }

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      if (appConfigs.length === 1) {
        setSelectedConfigId(appConfigs[0].id)
        setAccountLabel(appConfigs[0].label.toLowerCase())
      } else {
        setSelectedConfigId(NO_APP_CONFIG)
        setAccountLabel('')
      }
    }
  }, [open, appConfigs])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (accountLabel.trim()) {
      onSubmit(
        accountLabel.trim(),
        selectedConfigId !== NO_APP_CONFIG ? selectedConfigId : undefined
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Connect GitHub Account</DialogTitle>
            <DialogDescription>
              You'll be redirected to GitHub to authorize access.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="oauth-account-label">Account Label</Label>
              <Input
                id="oauth-account-label"
                value={accountLabel}
                onChange={(e) => setAccountLabel(e.target.value)}
                placeholder='e.g. "personal" or "work"'
                className="mt-1"
              />
              <p className="text-xs text-muted-foreground mt-1">
                A label to identify this connection. Must be unique per account.
              </p>
            </div>
            {appConfigs.length > 0 && (
              <div>
                <Label htmlFor="oauth-app-config">GitHub App</Label>
                <select
                  id="oauth-app-config"
                  value={selectedConfigId}
                  onChange={(e) => handleConfigChange(e.target.value)}
                  className="mt-1 flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value={NO_APP_CONFIG}>Default (global config)</option>
                  {appConfigs.map((config) => (
                    <option key={config.id} value={config.id}>
                      {config.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!accountLabel.trim() || isLoading}
            >
              {isLoading ? 'Connecting...' : 'Connect'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
