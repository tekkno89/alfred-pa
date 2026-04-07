import { useState } from 'react'
import { FolderGit2, Plus, Pencil, Trash2, X, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { useUserRepos, useAddUserRepo, useUpdateUserRepo, useDeleteUserRepo } from '@/hooks/useUserRepos'
import { useGitHubConnections } from '@/hooks/useGitHub'
import { ApiRequestError } from '@/lib/api'

export function RepoRegistryCard() {
  const { data, isLoading } = useUserRepos()
  const { data: ghData } = useGitHubConnections()
  const addRepo = useAddUserRepo()
  const updateRepo = useUpdateUserRepo()
  const deleteRepo = useDeleteUserRepo()

  const [showAddForm, setShowAddForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Add form state
  const [newOwner, setNewOwner] = useState('')
  const [newRepoName, setNewRepoName] = useState('')
  const [newAlias, setNewAlias] = useState('')
  const [newAccountLabel, setNewAccountLabel] = useState('')

  // Edit form state
  const [editAlias, setEditAlias] = useState('')
  const [editAccountLabel, setEditAccountLabel] = useState('')

  const repos = data?.items ?? []
  const ghConnections = ghData?.connections ?? []
  const accountLabels = [...new Set(ghConnections.map(c => c.account_label))]

  const resetAddForm = () => {
    setNewOwner('')
    setNewRepoName('')
    setNewAlias('')
    setNewAccountLabel('')
    setShowAddForm(false)
    setError(null)
  }

  const handleAdd = async () => {
    if (!newOwner.trim() || !newRepoName.trim()) return
    setError(null)
    try {
      await addRepo.mutateAsync({
        owner: newOwner.trim(),
        repo_name: newRepoName.trim(),
        alias: newAlias.trim() || null,
        github_account_label: newAccountLabel || null,
      })
      resetAddForm()
    } catch (e) {
      if (e instanceof ApiRequestError) {
        setError(e.detail)
      } else {
        setError('Failed to add repository')
      }
    }
  }

  const startEditing = (repo: typeof repos[0]) => {
    setEditingId(repo.id)
    setEditAlias(repo.alias ?? '')
    setEditAccountLabel(repo.github_account_label ?? '')
    setError(null)
  }

  const handleUpdate = async (id: string) => {
    setError(null)
    try {
      await updateRepo.mutateAsync({
        id,
        data: {
          alias: editAlias.trim() || null,
          github_account_label: editAccountLabel || null,
        },
      })
      setEditingId(null)
    } catch (e) {
      if (e instanceof ApiRequestError) {
        setError(e.detail)
      } else {
        setError('Failed to update repository')
      }
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteRepo.mutateAsync(id)
    } catch {
      setError('Failed to remove repository')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FolderGit2 className="h-5 w-5" />
          Repositories
        </CardTitle>
        <CardDescription>
          Register repos so you can reference them by short name or alias in chat
          instead of typing the full owner/repo.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-muted-foreground">Loading...</div>
        ) : (
          <div className="space-y-4">
            {error && (
              <div className="text-sm text-red-500 bg-red-500/10 rounded p-2">
                {error}
              </div>
            )}

            {/* Repo list */}
            {repos.length > 0 ? (
              <div className="space-y-2">
                {repos.map((repo) => (
                  <div
                    key={repo.id}
                    className="flex items-center justify-between rounded-md border p-3"
                  >
                    {editingId === repo.id ? (
                      <div className="flex-1 space-y-2">
                        <div className="text-sm font-medium">{repo.full_name}</div>
                        <div className="flex items-center gap-2">
                          <Input
                            className="h-8 text-sm w-32"
                            placeholder="Alias"
                            value={editAlias}
                            onChange={(e) => setEditAlias(e.target.value)}
                          />
                          <select
                            className="h-8 rounded border bg-background px-2 text-sm"
                            value={editAccountLabel}
                            onChange={(e) => setEditAccountLabel(e.target.value)}
                          >
                            <option value="">No account</option>
                            {accountLabels.map((label) => (
                              <option key={label} value={label}>
                                {label}
                              </option>
                            ))}
                          </select>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleUpdate(repo.id)}
                            disabled={updateRepo.isPending}
                          >
                            <Check className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setEditingId(null)}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm">{repo.full_name}</span>
                          {repo.alias && (
                            <Badge variant="secondary" className="text-xs">
                              {repo.alias}
                            </Badge>
                          )}
                          {repo.github_account_label && (
                            <Badge variant="outline" className="text-xs">
                              {repo.github_account_label}
                            </Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => startEditing(repo)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDelete(repo.id)}
                            disabled={deleteRepo.isPending}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            ) : !showAddForm && (
              <p className="text-sm text-muted-foreground">
                No repositories registered yet.
              </p>
            )}

            {/* Add form */}
            {showAddForm ? (
              <div className="space-y-3 rounded-md border p-3">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs text-muted-foreground">Owner</label>
                    <Input
                      className="h-8 text-sm"
                      placeholder="e.g. myorg"
                      value={newOwner}
                      onChange={(e) => setNewOwner(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Repository</label>
                    <Input
                      className="h-8 text-sm"
                      placeholder="e.g. my-repo"
                      value={newRepoName}
                      onChange={(e) => setNewRepoName(e.target.value)}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs text-muted-foreground">
                      Alias <span className="text-muted-foreground/60">(optional)</span>
                    </label>
                    <Input
                      className="h-8 text-sm"
                      placeholder="e.g. alfred"
                      value={newAlias}
                      onChange={(e) => setNewAlias(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">
                      GitHub Account <span className="text-muted-foreground/60">(optional)</span>
                    </label>
                    <select
                      className="h-8 w-full rounded border bg-background px-2 text-sm"
                      value={newAccountLabel}
                      onChange={(e) => setNewAccountLabel(e.target.value)}
                    >
                      <option value="">Default</option>
                      {accountLabels.map((label) => (
                        <option key={label} value={label}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    onClick={handleAdd}
                    disabled={addRepo.isPending || !newOwner.trim() || !newRepoName.trim()}
                  >
                    {addRepo.isPending ? 'Adding...' : 'Add'}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={resetAddForm}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setError(null)
                  setShowAddForm(true)
                }}
              >
                <Plus className="h-4 w-4 mr-2" />
                Add Repository
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
