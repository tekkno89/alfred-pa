import { useState } from 'react'
import { Calendar, Link2, Unlink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ConnectGoogleCalendarModal } from './ConnectGoogleCalendarModal'
import {
  useGoogleCalendarConnections,
  useRemoveGoogleCalendarConnection,
  useConnectGoogleCalendarOAuth,
} from '@/hooks/useGoogleCalendar'

export function GoogleCalendarConnectionCard() {
  const [oauthModalOpen, setOAuthModalOpen] = useState(false)

  const { data, isLoading } = useGoogleCalendarConnections()
  const removeMutation = useRemoveGoogleCalendarConnection()
  const connectOAuthMutation = useConnectGoogleCalendarOAuth()

  const connections = data?.connections ?? []

  const handleConnectOAuth = (accountLabel: string) => {
    connectOAuthMutation.mutate({ accountLabel })
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Calendar className="h-5 w-5" />
            Google Calendar
          </CardTitle>
          <CardDescription>
            Connect your Google account to let Alfred view your calendar and
            help manage your schedule.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="text-muted-foreground">Loading...</div>
          ) : (
            <div className="space-y-3">
              {connections.length > 0 ? (
                <div className="space-y-3">
                  {connections.map((conn) => (
                    <div
                      key={conn.id}
                      className="flex items-center justify-between rounded-md border p-3"
                    >
                      <div className="flex items-center gap-3">
                        <div className="h-2 w-2 rounded-full bg-green-500" />
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-sm">
                              {conn.external_account_id || conn.account_label}
                            </span>
                            {conn.account_label !== 'default' && (
                              <Badge variant="outline" className="text-xs">
                                {conn.account_label}
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeMutation.mutate(conn.id)}
                        disabled={removeMutation.isPending}
                      >
                        <Unlink className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <div className="h-2 w-2 rounded-full bg-gray-400" />
                  <span>No Google accounts connected</span>
                </div>
              )}

              <Button
                onClick={() => setOAuthModalOpen(true)}
                variant="default"
                size="sm"
              >
                <Link2 className="h-4 w-4 mr-2" />
                Connect Google Calendar
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <ConnectGoogleCalendarModal
        open={oauthModalOpen}
        onOpenChange={setOAuthModalOpen}
        onSubmit={handleConnectOAuth}
        isLoading={connectOAuthMutation.isPending}
      />
    </>
  )
}
