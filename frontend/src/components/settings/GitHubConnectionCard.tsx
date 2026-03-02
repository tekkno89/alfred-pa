import { useState } from 'react'
import { Github, Link2, Unlink, Key, Settings2, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { AddPATModal } from './AddPATModal'
import { AddGitHubAppModal } from './AddGitHubAppModal'
import { ConnectGitHubModal } from './ConnectGitHubModal'
import {
  useGitHubConnections,
  useAddGitHubPAT,
  useRemoveGitHubConnection,
  useConnectGitHubOAuth,
  useGitHubAppConfigs,
  useCreateGitHubAppConfig,
  useDeleteGitHubAppConfig,
} from '@/hooks/useGitHub'
import { ApiRequestError } from '@/lib/api'

export function GitHubConnectionCard() {
  const [patModalOpen, setPATModalOpen] = useState(false)
  const [patError, setPATError] = useState<string | null>(null)
  const [appModalOpen, setAppModalOpen] = useState(false)
  const [appError, setAppError] = useState<string | null>(null)
  const [oauthModalOpen, setOAuthModalOpen] = useState(false)

  const { data, isLoading } = useGitHubConnections()
  const { data: appConfigsData, isLoading: appConfigsLoading } = useGitHubAppConfigs()
  const addPATMutation = useAddGitHubPAT()
  const removeMutation = useRemoveGitHubConnection()
  const connectOAuthMutation = useConnectGitHubOAuth()
  const createAppConfigMutation = useCreateGitHubAppConfig()
  const deleteAppConfigMutation = useDeleteGitHubAppConfig()

  const connections = data?.connections ?? []
  const appConfigs = appConfigsData?.configs ?? []

  const handleAddPAT = async (token: string, accountLabel: string) => {
    setPATError(null)
    try {
      await addPATMutation.mutateAsync({ token, account_label: accountLabel })
      setPATModalOpen(false)
    } catch (error) {
      if (error instanceof ApiRequestError) {
        setPATError(error.detail)
      } else {
        setPATError('Failed to add token')
      }
    }
  }

  const handleAddAppConfig = async (data: {
    label: string
    client_id: string
    client_secret: string
    github_app_id?: string
  }) => {
    setAppError(null)
    try {
      await createAppConfigMutation.mutateAsync({
        label: data.label,
        client_id: data.client_id,
        client_secret: data.client_secret,
        github_app_id: data.github_app_id || null,
      })
      setAppModalOpen(false)
    } catch (error) {
      if (error instanceof ApiRequestError) {
        setAppError(error.detail)
      } else {
        setAppError('Failed to register app')
      }
    }
  }

  const handleConnectOAuth = (accountLabel: string, appConfigId?: string) => {
    connectOAuthMutation.mutate({ accountLabel, appConfigId })
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Github className="h-5 w-5" />
            GitHub
          </CardTitle>
          <CardDescription>
            Connect your GitHub account for code review, PR creation, and repository access.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading || appConfigsLoading ? (
            <div className="text-muted-foreground">Loading...</div>
          ) : (
            <div className="space-y-6">
              {/* GitHub Apps Section */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-medium flex items-center gap-1.5">
                    <Settings2 className="h-4 w-4" />
                    GitHub Apps
                  </h4>
                  <Button
                    onClick={() => {
                      setAppError(null)
                      setAppModalOpen(true)
                    }}
                    variant="outline"
                    size="sm"
                  >
                    Register GitHub App
                  </Button>
                </div>
                {appConfigs.length > 0 ? (
                  <div className="space-y-2">
                    {appConfigs.map((config) => (
                      <div
                        key={config.id}
                        className="flex items-center justify-between rounded-md border p-3"
                      >
                        <div>
                          <span className="font-medium text-sm">{config.label}</span>
                          <span className="text-xs text-muted-foreground ml-2 font-mono">
                            {config.client_id.slice(0, 8)}...
                          </span>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => deleteAppConfigMutation.mutate(config.id)}
                          disabled={deleteAppConfigMutation.isPending}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    No GitHub Apps registered. Register one to use OAuth with your own app, or use the global configuration.
                  </p>
                )}
              </div>

              {/* Divider */}
              <div className="border-t" />

              {/* Connected Accounts Section */}
              <div className="space-y-3">
                <h4 className="text-sm font-medium">Connected Accounts</h4>
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
                              <Badge variant="secondary" className="text-xs">
                                {conn.token_type === 'pat' ? 'PAT' : 'OAuth'}
                              </Badge>
                              {conn.account_label !== 'default' && (
                                <Badge variant="outline" className="text-xs">
                                  {conn.account_label}
                                </Badge>
                              )}
                              {conn.app_config_label && (
                                <Badge variant="outline" className="text-xs">
                                  via {conn.app_config_label}
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
                    <span>No GitHub accounts connected</span>
                  </div>
                )}

                <div className="flex gap-2">
                  <Button
                    onClick={() => setOAuthModalOpen(true)}
                    variant="default"
                    size="sm"
                  >
                    <Link2 className="h-4 w-4 mr-2" />
                    Connect with GitHub
                  </Button>
                  <Button
                    onClick={() => {
                      setPATError(null)
                      setPATModalOpen(true)
                    }}
                    variant="outline"
                    size="sm"
                  >
                    <Key className="h-4 w-4 mr-2" />
                    Add Token
                  </Button>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <ConnectGitHubModal
        open={oauthModalOpen}
        onOpenChange={setOAuthModalOpen}
        onSubmit={handleConnectOAuth}
        appConfigs={appConfigs}
        isLoading={connectOAuthMutation.isPending}
      />

      <AddPATModal
        open={patModalOpen}
        onOpenChange={setPATModalOpen}
        onSubmit={handleAddPAT}
        isLoading={addPATMutation.isPending}
        error={patError}
      />

      <AddGitHubAppModal
        open={appModalOpen}
        onOpenChange={setAppModalOpen}
        onSubmit={handleAddAppConfig}
        isLoading={createAppConfigMutation.isPending}
        error={appError}
      />
    </>
  )
}
