import { useNavigate } from 'react-router-dom'
import { Inbox, AlertTriangle, Clock, Archive, Settings } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { useTriageSettings, useTriageSessionStats, useClassifications } from '@/hooks/useTriage'

const URGENCY_STYLES: Record<string, { bg: string; text: string }> = {
  urgent: {
    bg: 'bg-red-100 dark:bg-red-900/40',
    text: 'text-red-800 dark:text-red-200',
  },
  digest: {
    bg: 'bg-slate-100 dark:bg-slate-800',
    text: 'text-slate-700 dark:text-slate-300',
  },
  digest_summary: {
    bg: 'bg-blue-100 dark:bg-blue-900/40',
    text: 'text-blue-800 dark:text-blue-200',
  },
  noise: {
    bg: 'bg-gray-100 dark:bg-gray-800',
    text: 'text-gray-500 dark:text-gray-400',
  },
  review: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/40',
    text: 'text-yellow-800 dark:text-yellow-200',
  },
}

export function TriageCard() {
  const navigate = useNavigate()
  const { data: settings, isLoading: loadingSettings } = useTriageSettings()
  const { data: stats, isLoading: loadingStats } = useTriageSessionStats()
  const { data: recent } = useClassifications({ limit: 5, urgency: 'reviewable', reviewed: false })

  const isActive = settings?.is_always_on ?? false

  if (loadingSettings || loadingStats) {
    return (
      <Card className="hover:shadow-md transition-shadow h-full flex flex-col">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Inbox className="h-4 w-4" />
            Slack Triage
          </CardTitle>
        </CardHeader>
        <CardContent className="flex-1">
          <p className="text-sm text-muted-foreground">Loading...</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card
      className="hover:shadow-md transition-shadow h-full flex flex-col cursor-pointer"
      onClick={() => navigate('/triage')}
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Inbox className="h-4 w-4" />
          Slack Triage
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto">
        {!isActive ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Triage is currently inactive. Enable always-on mode or start a focus session to classify incoming Slack messages.
            </p>
            <button
              className="text-xs text-primary hover:underline flex items-center gap-1"
              onClick={(e) => {
                e.stopPropagation()
                navigate('/settings/triage')
              }}
            >
              <Settings className="h-3 w-3" />
              Configure Triage
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Stats row */}
            {stats && stats.total > 0 && (
              <div className="flex gap-2 text-xs">
                <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200">
                  <AlertTriangle className="h-3 w-3" />
                  {stats.urgent}
                </span>
                <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200">
                  <Clock className="h-3 w-3" />
                  {stats.review}
                </span>
                <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                  <Archive className="h-3 w-3" />
                  {stats.digest}
                </span>
              </div>
            )}

            {/* Recent classifications */}
            {recent && recent.items.length > 0 ? (
              <div className="space-y-1.5">
                {recent.items.map((item) => {
                  const style = URGENCY_STYLES[item.urgency_level] ?? URGENCY_STYLES.digest
                  return (
                    <div key={item.id} className="flex items-start gap-2">
                      <span
                        className={`shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium ${style.bg} ${style.text}`}
                      >
                        {item.urgency_level === 'digest_summary' ? 'digest' : item.urgency_level}
                      </span>
                      <span className="text-sm truncate flex-1">
                        {item.abstract || 'Message'}
                      </span>
                    </div>
                  )
                })}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No recent classifications</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
