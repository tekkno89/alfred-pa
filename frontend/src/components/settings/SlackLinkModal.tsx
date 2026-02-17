import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

interface SlackLinkModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (code: string) => Promise<void>
  isLoading: boolean
  error: string | null
}

export function SlackLinkModal({
  open,
  onOpenChange,
  onSubmit,
  isLoading,
  error,
}: SlackLinkModalProps) {
  const [code, setCode] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (code.length === 6) {
      await onSubmit(code)
      setCode('')
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <form onSubmit={handleSubmit}>
          <AlertDialogHeader>
            <AlertDialogTitle>Link Slack Account</AlertDialogTitle>
            <AlertDialogDescription>
              Enter the 6-character code from the /alfred-link Slack command.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="py-4">
            <Label htmlFor="code">Linking Code</Label>
            <Input
              id="code"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder="ABC123"
              maxLength={6}
              className="font-mono text-lg tracking-widest text-center mt-2"
              autoComplete="off"
            />
            {error && (
              <p className="text-sm text-destructive mt-2">{error}</p>
            )}
            <p className="text-sm text-muted-foreground mt-2">
              To get a code, type <code>/alfred-link</code> in Slack.
            </p>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel type="button" disabled={isLoading}>
              Cancel
            </AlertDialogCancel>
            <Button type="submit" disabled={code.length !== 6 || isLoading}>
              {isLoading ? 'Linking...' : 'Link Account'}
            </Button>
          </AlertDialogFooter>
        </form>
      </AlertDialogContent>
    </AlertDialog>
  )
}
