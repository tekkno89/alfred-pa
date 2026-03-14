import { Archive, ArchiveRestore, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  useYouTubeAllPlaylists,
  useDeletePlaylist,
  useArchivePlaylist,
  useUnarchivePlaylist,
} from '@/hooks/useYouTube'

interface ManagePlaylistsModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ManagePlaylistsModal({ open, onOpenChange }: ManagePlaylistsModalProps) {
  const { data } = useYouTubeAllPlaylists()
  const deletePlaylist = useDeletePlaylist()
  const archivePlaylist = useArchivePlaylist()
  const unarchivePlaylist = useUnarchivePlaylist()

  const playlists = data?.playlists ?? []

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Delete "${name}" and all its videos? This cannot be undone.`)) return
    await deletePlaylist.mutateAsync(id)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Manage Playlists</DialogTitle>
        </DialogHeader>

        <div className="space-y-2 max-h-80 overflow-y-auto">
          {playlists.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No playlists yet.
            </p>
          ) : (
            playlists.map((playlist) => (
              <div
                key={playlist.id}
                className={
                  'flex items-center justify-between rounded-md border px-3 py-2' +
                  (playlist.is_archived ? ' opacity-60' : '')
                }
              >
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium truncate block">
                    {playlist.name}
                  </span>
                  <div className="flex gap-2 text-xs text-muted-foreground">
                    {playlist.is_active && <span>Active</span>}
                    {playlist.is_archived && <span>Archived</span>}
                  </div>
                </div>

                <div className="flex items-center gap-1 shrink-0 ml-2">
                  {playlist.is_archived ? (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => unarchivePlaylist.mutate(playlist.id)}
                      disabled={unarchivePlaylist.isPending}
                      title="Unarchive"
                    >
                      <ArchiveRestore className="h-3.5 w-3.5" />
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => archivePlaylist.mutate(playlist.id)}
                      disabled={archivePlaylist.isPending}
                      title="Archive"
                    >
                      <Archive className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-destructive hover:text-destructive"
                    onClick={() => handleDelete(playlist.id, playlist.name)}
                    disabled={deletePlaylist.isPending}
                    title="Delete"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
