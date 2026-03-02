import { useState } from 'react'
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

interface AddGitHubAppModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (data: {
    label: string
    client_id: string
    client_secret: string
    github_app_id?: string
  }) => Promise<void>
  isLoading: boolean
  error: string | null
}

export function AddGitHubAppModal({
  open,
  onOpenChange,
  onSubmit,
  isLoading,
  error,
}: AddGitHubAppModalProps) {
  const [label, setLabel] = useState('')
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [githubAppId, setGithubAppId] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (label.trim() && clientId.trim() && clientSecret.trim()) {
      await onSubmit({
        label: label.trim(),
        client_id: clientId.trim(),
        client_secret: clientSecret.trim(),
        github_app_id: githubAppId.trim() || undefined,
      })
      setLabel('')
      setClientId('')
      setClientSecret('')
      setGithubAppId('')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Register GitHub App</DialogTitle>
            <DialogDescription>
              Register your own GitHub App for OAuth access. Set the callback URL
              in your GitHub App settings to:{' '}
              <code className="text-xs bg-muted px-1 py-0.5 rounded">
                {window.location.origin}/api/github/oauth/callback
              </code>
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="app-label">Label</Label>
              <Input
                id="app-label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder='e.g. "Personal" or "Work"'
                className="mt-1"
              />
              <p className="text-xs text-muted-foreground mt-1">
                A name to identify this GitHub App configuration.
              </p>
            </div>
            <div>
              <Label htmlFor="app-client-id">Client ID</Label>
              <Input
                id="app-client-id"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                placeholder="Iv1.abc123..."
                className="font-mono mt-1"
              />
            </div>
            <div>
              <Label htmlFor="app-client-secret">Client Secret</Label>
              <Input
                id="app-client-secret"
                type="password"
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
                placeholder="Enter client secret"
                className="font-mono mt-1"
                autoComplete="off"
              />
              <p className="text-xs text-muted-foreground mt-1">
                The secret will be encrypted before storage.
              </p>
            </div>
            <div>
              <Label htmlFor="app-github-app-id">GitHub App ID (optional)</Label>
              <Input
                id="app-github-app-id"
                value={githubAppId}
                onChange={(e) => setGithubAppId(e.target.value)}
                placeholder="123456"
                className="mt-1"
              />
            </div>
            {error && (
              <p className="text-sm text-destructive">{error}</p>
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
              disabled={
                !label.trim() ||
                !clientId.trim() ||
                !clientSecret.trim() ||
                isLoading
              }
            >
              {isLoading ? 'Registering...' : 'Register App'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
