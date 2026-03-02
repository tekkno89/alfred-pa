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

interface AddPATModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (token: string, accountLabel: string) => Promise<void>
  isLoading: boolean
  error: string | null
}

export function AddPATModal({
  open,
  onOpenChange,
  onSubmit,
  isLoading,
  error,
}: AddPATModalProps) {
  const [token, setToken] = useState('')
  const [accountLabel, setAccountLabel] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (token.trim()) {
      await onSubmit(token.trim(), accountLabel.trim() || 'default')
      setToken('')
      setAccountLabel('')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Add Personal Access Token</DialogTitle>
            <DialogDescription>
              Enter a GitHub Personal Access Token (classic or fine-grained).
              The token will be encrypted before storage.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="pat-token">Token</Label>
              <Input
                id="pat-token"
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="ghp_xxxxxxxxxxxx"
                className="font-mono mt-1"
                autoComplete="off"
              />
            </div>
            <div>
              <Label htmlFor="account-label">Account Label</Label>
              <Input
                id="account-label"
                value={accountLabel}
                onChange={(e) => setAccountLabel(e.target.value)}
                placeholder="default"
                className="mt-1"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Use labels like "personal" or "work" to distinguish multiple accounts.
              </p>
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
            <Button type="submit" disabled={!token.trim() || isLoading}>
              {isLoading ? 'Adding...' : 'Add Token'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
