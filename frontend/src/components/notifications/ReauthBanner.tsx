import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { apiGet } from '@/lib/api'
import type { SlackOAuthStatusResponse } from '@/types'

export function ReauthBanner() {
  const [dismissed, setDismissed] = useState(false)

  const { data: oauthStatus } = useQuery({
    queryKey: ['slack-oauth-status'],
    queryFn: () => apiGet<SlackOAuthStatusResponse>('/auth/slack/oauth/status'),
    staleTime: 5 * 60 * 1000, // 5 minutes — shared cache with IntegrationsPage
  })

  if (dismissed || !oauthStatus?.reauth_required) return null

  return (
    <div className="fixed top-0 left-0 right-0 z-[90] bg-amber-500 text-white px-4 py-2 flex items-center justify-between">
      <div className="flex items-center gap-2 text-sm">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <span>
          Alfred needs updated Slack permissions.{' '}
          <Link to="/settings/integrations" className="underline font-medium">
            Re-authorize in Settings
          </Link>
        </span>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setDismissed(true)}
        className="text-white hover:bg-amber-600 shrink-0 h-6 w-6 p-0"
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  )
}
