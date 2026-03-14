import { useState, useEffect } from 'react'
import { Youtube } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  useYouTubePlaylists,
  useCreatePlaylist,
  useAddVideo,
  useFetchYouTubeMetadata,
} from '@/hooks/useYouTube'

interface AddVideoModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  activePlaylistId?: string | null
}

export function AddVideoModal({ open, onOpenChange, activePlaylistId }: AddVideoModalProps) {
  const { data: playlistsData } = useYouTubePlaylists()
  const createPlaylist = useCreatePlaylist()
  const addVideo = useAddVideo()

  const [url, setUrl] = useState('')
  const [debouncedUrl, setDebouncedUrl] = useState('')
  const [selectedPlaylistId, setSelectedPlaylistId] = useState<string>('')
  const [addToTop, setAddToTop] = useState(false)
  const [newPlaylistName, setNewPlaylistName] = useState('')
  const [showNewPlaylist, setShowNewPlaylist] = useState(false)

  const { data: metadata, isFetching: metadataLoading } = useFetchYouTubeMetadata(debouncedUrl)

  // Debounce URL input
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedUrl(url), 500)
    return () => clearTimeout(timer)
  }, [url])

  // Pre-select active playlist
  useEffect(() => {
    if (activePlaylistId && !selectedPlaylistId) {
      setSelectedPlaylistId(activePlaylistId)
    } else if (playlistsData?.playlists.length && !selectedPlaylistId) {
      const active = playlistsData.playlists.find((p) => p.is_active)
      if (active) setSelectedPlaylistId(active.id)
      else setSelectedPlaylistId(playlistsData.playlists[0].id)
    }
  }, [activePlaylistId, playlistsData, selectedPlaylistId])

  // Reset form when dialog closes
  useEffect(() => {
    if (!open) {
      setUrl('')
      setDebouncedUrl('')
      setAddToTop(false)
      setNewPlaylistName('')
      setShowNewPlaylist(false)
    }
  }, [open])

  const handleSubmit = async () => {
    if (!url.trim()) return

    let playlistId = selectedPlaylistId

    // Create new playlist if needed
    if (showNewPlaylist && newPlaylistName.trim()) {
      const newPlaylist = await createPlaylist.mutateAsync({
        name: newPlaylistName.trim(),
        is_active: true,
      })
      playlistId = newPlaylist.id
    }

    if (!playlistId) return

    await addVideo.mutateAsync({
      playlist_id: playlistId,
      youtube_url: url.trim(),
      add_to_top: addToTop,
    })

    onOpenChange(false)
  }

  const playlists = playlistsData?.playlists ?? []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Video</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {/* Playlist selector */}
          <div className="space-y-2">
            <Label>Playlist</Label>
            {showNewPlaylist ? (
              <div className="flex gap-2">
                <Input
                  placeholder="New playlist name"
                  value={newPlaylistName}
                  onChange={(e) => setNewPlaylistName(e.target.value)}
                  autoFocus
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowNewPlaylist(false)}
                >
                  Cancel
                </Button>
              </div>
            ) : (
              <Select
                value={selectedPlaylistId}
                onValueChange={(val) => {
                  if (val === '__new__') {
                    setShowNewPlaylist(true)
                  } else {
                    setSelectedPlaylistId(val)
                  }
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select playlist" />
                </SelectTrigger>
                <SelectContent>
                  {playlists.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}{p.is_active ? ' (active)' : ''}
                    </SelectItem>
                  ))}
                  <SelectItem value="__new__">+ New Playlist</SelectItem>
                </SelectContent>
              </Select>
            )}
          </div>

          {/* URL input */}
          <div className="space-y-2">
            <Label>YouTube URL</Label>
            <Input
              placeholder="https://www.youtube.com/watch?v=..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>

          {/* Metadata preview */}
          {metadataLoading && (
            <p className="text-sm text-muted-foreground">Fetching metadata...</p>
          )}
          {metadata && metadata.title && (
            <div className="flex gap-3 p-2 rounded-md bg-muted">
              {metadata.thumbnail_url ? (
                <img
                  src={metadata.thumbnail_url}
                  alt={metadata.title}
                  className="w-24 h-auto rounded object-cover shrink-0"
                />
              ) : (
                <div className="w-24 h-16 rounded bg-muted-foreground/20 flex items-center justify-center shrink-0">
                  <Youtube className="h-6 w-6 text-muted-foreground" />
                </div>
              )}
              <div className="min-w-0">
                <p className="text-sm font-medium line-clamp-2">{metadata.title}</p>
                {metadata.youtube_video_id && (
                  <p className="text-xs text-muted-foreground mt-1">ID: {metadata.youtube_video_id}</p>
                )}
              </div>
            </div>
          )}

          {/* Add to top toggle */}
          <div className="flex items-center justify-between">
            <Label htmlFor="add-to-top">Add to top of playlist</Label>
            <Switch
              id="add-to-top"
              checked={addToTop}
              onCheckedChange={setAddToTop}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={
              !url.trim() ||
              addVideo.isPending ||
              createPlaylist.isPending ||
              (!selectedPlaylistId && !showNewPlaylist)
            }
          >
            {addVideo.isPending ? 'Adding...' : 'Add Video'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
