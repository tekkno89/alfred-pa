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

interface ConnectGoogleCalendarModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (accountLabel: string) => void
  isLoading: boolean
}

export function ConnectGoogleCalendarModal({
  open,
  onOpenChange,
  onSubmit,
  isLoading,
}: ConnectGoogleCalendarModalProps) {
  const [accountLabel, setAccountLabel] = useState('')

  useEffect(() => {
    if (open) {
      setAccountLabel('')
    }
  }, [open])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (accountLabel.trim()) {
      onSubmit(accountLabel.trim())
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Connect Google Calendar</DialogTitle>
            <DialogDescription>
              You'll be redirected to Google to authorize calendar access
              (read-only).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="gcal-account-label">Account Label</Label>
              <Input
                id="gcal-account-label"
                value={accountLabel}
                onChange={(e) => setAccountLabel(e.target.value)}
                placeholder='e.g. "personal" or "work"'
                className="mt-1"
              />
              <p className="text-xs text-muted-foreground mt-1">
                A label to identify this Google account. Must be unique per
                account.
              </p>
            </div>
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
