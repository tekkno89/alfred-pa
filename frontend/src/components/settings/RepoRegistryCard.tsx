import { useState } from 'react'
import { FolderGit2, Plus, Pencil, Trash2, X, Check, Download, Lock, Globe, Loader2, Shield, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  useUserRepos, useAddUserRepo, useUpdateUserRepo, useDeleteUserRepo,
  useAvailableRepos, useImportRepos,
} from '@/hooks/useUserRepos'
import { useGitHubConnections } from '@/hooks/useGitHub'
import { ApiRequestError } from '@/lib/api'
import type { AvailableRepo } from '@/types'

/** Summarize permissions into a short human-readable string. */
function formatPermissions(perms: Record<string, string>): string {
  const entries = Object.entries(perms)
    .filter(([key]) => key !== 'metadata')
    .sort(([a], [b]) => a.localeCompare(b))
  if (entries.length === 0) return 'metadata only'
  return entries.map(([key, val]) => `${key}: ${val}`).join(', ')
}

/** Color code for permission level. */
function permissionColor(level: string): string {
  if (level === 'write' || level === 'admin') return 'text-amber-600 dark:text-amber-400'
  return 'text-muted-foreground'
}

export function RepoRegistryCard() {
  const { data, isLoading } = useUserRepos()
  const { data: ghData } = useGitHubConnections()
  const addRepo = useAddUserRepo()
  const updateRepo = useUpdateUserRepo()
  const deleteRepo = useDeleteUserRepo()
  const importRepos = useImportRepos()

  const [showAddForm, setShowAddForm] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedImports, setSelectedImports] = useState<Set<string>>(new Set())
  const [expandedPerms, setExpandedPerms] = useState<string | null>(null)

  // Add form state
  const [newOwner, setNewOwner] = useState('')
  const [newRepoName, setNewRepoName] = useState('')
  const [newAlias, setNewAlias] = useState('')
  const [newAccountLabel, setNewAccountLabel] = useState('')

  // Edit form state
  const [editAlias, setEditAlias] = useState('')
  const [editAccountLabel, setEditAccountLabel] = useState('')

  // Only fetch available repos when import panel is open
  const { data: availableData, isLoading: availableLoading } = useAvailableRepos(showImport)

  const repos = data?.items ?? []
  const ghConnections = ghData?.connections ?? []
  const accountLabels = [...new Set(ghConnections.map(c => c.account_label))]
  const availableRepos = availableData?.items ?? []
  const unregistered = availableRepos.filter(r => !r.already_registered)

  // Build a lookup for permissions from available repos data
  const permsByFullName = new Map(
    availableRepos.map(r => [r.full_name.toLowerCase(), r])
  )

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

  const toggleImportSelection = (fullName: string) => {
    setSelectedImports(prev => {
      const next = new Set(prev)
      if (next.has(fullName)) {
        next.delete(fullName)
      } else {
        next.add(fullName)
      }
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedImports.size === unregistered.length) {
      setSelectedImports(new Set())
    } else {
      setSelectedImports(new Set(unregistered.map(r => r.full_name)))
    }
  }

  const handleImport = async () => {
    if (selectedImports.size === 0) return
    setError(null)

    const reposToImport = availableRepos
      .filter(r => selectedImports.has(r.full_name))
      .map((r: AvailableRepo) => ({
        owner: r.owner,
        repo_name: r.repo_name,
        github_account_label: r.account_label,
      }))

    try {
      const result = await importRepos.mutateAsync({ repos: reposToImport })
      setSelectedImports(new Set())
      setShowImport(false)
      if (result.imported > 0) {
        setError(null)
      }
    } catch (e) {
      if (e instanceof ApiRequestError) {
        setError(e.detail)
      } else {
        setError('Failed to import repositories')
      }
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
                        <div className="flex items-center gap-2 flex-1 min-w-0">
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
                          {(() => {
                            const avail = permsByFullName.get(repo.full_name.toLowerCase())
                            if (!avail) return null
                            return (
                              <span className="text-xs text-muted-foreground" title={formatPermissions(avail.permissions)}>
                                <Shield className="h-3 w-3 inline mr-0.5" />
                                {formatPermissions(avail.permissions)}
                              </span>
                            )
                          })()}
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
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
            ) : !showAddForm && !showImport && (
              <p className="text-sm text-muted-foreground">
                No repositories registered yet.
              </p>
            )}

            {/* Import from GitHub panel */}
            {showImport && (
              <div className="space-y-3 rounded-md border p-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-medium">Import from GitHub</h4>
                  <Button variant="ghost" size="sm" onClick={() => {
                    setShowImport(false)
                    setSelectedImports(new Set())
                  }}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>

                {availableLoading ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground py-4 justify-center">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Fetching repos from GitHub...
                  </div>
                ) : unregistered.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-2">
                    {availableRepos.length === 0
                      ? 'No repos found. Make sure your GitHub App has repository access configured.'
                      : 'All available repos are already registered.'}
                  </p>
                ) : (
                  <>
                    <div className="flex items-center justify-between">
                      <button
                        onClick={toggleSelectAll}
                        className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                      >
                        {selectedImports.size === unregistered.length ? 'Deselect all' : 'Select all'}
                      </button>
                      <span className="text-xs text-muted-foreground">
                        {unregistered.length} available
                      </span>
                    </div>
                    <div className="max-h-80 overflow-y-auto space-y-1">
                      {unregistered.map((repo) => (
                        <div key={repo.full_name} className="rounded-md border">
                          <label
                            className="flex items-center gap-3 p-2 cursor-pointer hover:bg-muted/50 transition-colors"
                          >
                            <input
                              type="checkbox"
                              checked={selectedImports.has(repo.full_name)}
                              onChange={() => toggleImportSelection(repo.full_name)}
                              className="rounded"
                            />
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              {repo.private ? (
                                <Lock className="h-3 w-3 text-muted-foreground shrink-0" />
                              ) : (
                                <Globe className="h-3 w-3 text-muted-foreground shrink-0" />
                              )}
                              <span className="text-sm truncate">{repo.full_name}</span>
                            </div>
                            <button
                              onClick={(e) => {
                                e.preventDefault()
                                setExpandedPerms(expandedPerms === repo.full_name ? null : repo.full_name)
                              }}
                              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground shrink-0"
                              title="View permissions"
                            >
                              <Shield className="h-3 w-3" />
                              <ChevronRight className={`h-3 w-3 transition-transform ${expandedPerms === repo.full_name ? 'rotate-90' : ''}`} />
                            </button>
                            <Badge variant="outline" className="text-xs shrink-0">
                              {repo.account_label}
                            </Badge>
                          </label>
                          {expandedPerms === repo.full_name && (
                            <div className="px-9 pb-2 text-xs text-muted-foreground space-y-0.5">
                              <div className="flex items-center gap-1 mb-1">
                                <span className="font-medium">
                                  Permissions ({repo.permission_source === 'app' ? 'GitHub App' : repo.permission_source.toUpperCase()}):
                                </span>
                              </div>
                              {Object.entries(repo.permissions)
                                .filter(([key]) => key !== 'metadata')
                                .sort(([a], [b]) => a.localeCompare(b))
                                .map(([key, val]) => (
                                  <div key={key} className="flex items-center gap-2">
                                    <span>{key.replace(/_/g, ' ')}</span>
                                    <span className={permissionColor(val)}>{val}</span>
                                  </div>
                                ))}
                              {Object.keys(repo.permissions).filter(k => k !== 'metadata').length === 0 && (
                                <span>metadata only</span>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                    <Button
                      size="sm"
                      onClick={handleImport}
                      disabled={selectedImports.size === 0 || importRepos.isPending}
                    >
                      {importRepos.isPending
                        ? 'Importing...'
                        : `Import ${selectedImports.size} repo${selectedImports.size === 1 ? '' : 's'}`}
                    </Button>
                  </>
                )}
              </div>
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
            ) : !showImport && (
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setError(null)
                    setShowImport(true)
                  }}
                >
                  <Download className="h-4 w-4 mr-2" />
                  Import from GitHub
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setError(null)
                    setShowAddForm(true)
                  }}
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Add Manually
                </Button>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
