import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Youtube,
  Plus,
  GripVertical,
  Eye,
  Trash2,
  RotateCcw,
  SkipForward,
  MoreVertical,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  useYouTubePlaylists,
  useYouTubeVideos,
  useActivatePlaylist,
  useMarkVideoWatched,
  useMarkVideoDeleted,
  useRestoreVideo,
  useReorderVideos,
  useCreatePlaylist,
} from '@/hooks/useYouTube'
import { AddVideoModal } from '@/components/youtube/AddVideoModal'
import { ManagePlaylistsModal } from '@/components/youtube/ManagePlaylistsModal'
import type { YouTubeVideo } from '@/types'

// YouTube IFrame API types
interface YTPlayerOptions {
  videoId: string
  playerVars?: Record<string, number | string>
  events?: {
    onStateChange?: (event: { data: number }) => void
    onReady?: (event: { target: YTPlayer }) => void
  }
}

interface YTPlayer {
  loadVideoById: (config: string | { videoId: string; startSeconds?: number }) => void
  stopVideo: () => void
  destroy: () => void
  getCurrentTime: () => number
  seekTo: (seconds: number, allowSeekAhead: boolean) => void
}

interface YTConstructor {
  Player: new (el: HTMLDivElement, opts: YTPlayerOptions) => YTPlayer
  PlayerState: { ENDED: number }
}

declare global {
  interface Window {
    YT: YTConstructor
    onYouTubeIframeAPIReady: () => void
  }
}

type FilterTab = 'active' | 'watched' | 'deleted' | 'all'

const PROGRESS_KEY = 'youtube-progress'

function getProgressMap(): Record<string, number> {
  try {
    const raw = localStorage.getItem(PROGRESS_KEY)
    if (!raw) return {}
    return JSON.parse(raw) ?? {}
  } catch {
    return {}
  }
}

function saveProgress(videoId: string, time: number) {
  const map = getProgressMap()
  map[videoId] = time
  localStorage.setItem(PROGRESS_KEY, JSON.stringify(map))
}

function getProgress(videoId: string): number | null {
  const map = getProgressMap()
  const time = map[videoId]
  return typeof time === 'number' && time > 0 ? time : null
}

function clearProgress(videoId: string) {
  const map = getProgressMap()
  delete map[videoId]
  localStorage.setItem(PROGRESS_KEY, JSON.stringify(map))
}

export function YouTubePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [manageModalOpen, setManageModalOpen] = useState(false)
  const [filterTab, setFilterTab] = useState<FilterTab>('active')
  const [currentVideoId, setCurrentVideoId] = useState<string | null>(null)
  const [newPlaylistName, setNewPlaylistName] = useState('')
  const [showNewPlaylist, setShowNewPlaylist] = useState(false)

  // Drag state
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)
  const dragNodeRef = useRef<HTMLDivElement | null>(null)

  // YouTube IFrame API
  const playerRef = useRef<YTPlayer | null>(null)
  const playerContainerRef = useRef<HTMLDivElement>(null)
  const apiLoadedRef = useRef(false)

  const { data: playlistsData } = useYouTubePlaylists()
  const activatePlaylist = useActivatePlaylist()
  const createPlaylist = useCreatePlaylist()
  const markWatched = useMarkVideoWatched()
  const markDeleted = useMarkVideoDeleted()
  const restoreVideo = useRestoreVideo()
  const reorderVideos = useReorderVideos()

  const playlists = playlistsData?.playlists ?? []
  const activePlaylist = playlists.find((p) => p.is_active)
  const activePlaylistId = activePlaylist?.id ?? null

  const statusFilter = filterTab === 'all' ? 'all' : filterTab
  const { data: videosData } = useYouTubeVideos(activePlaylistId, statusFilter)
  const videos = videosData?.videos ?? []

  // Find the currently playing video object
  const currentVideo = videos.find((v) => v.youtube_video_id === currentVideoId) ?? null

  // Auto-open modal from URL param
  useEffect(() => {
    if (searchParams.get('add') === 'true') {
      setAddModalOpen(true)
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams])

  // Load YouTube IFrame API
  useEffect(() => {
    if (apiLoadedRef.current) return
    if (window.YT && window.YT.Player) {
      apiLoadedRef.current = true
      return
    }

    const tag = document.createElement('script')
    tag.src = 'https://www.youtube.com/iframe_api'
    const firstScript = document.getElementsByTagName('script')[0]
    firstScript.parentNode?.insertBefore(tag, firstScript)

    window.onYouTubeIframeAPIReady = () => {
      apiLoadedRef.current = true
    }
  }, [])

  // Pending start time for seeking when player loads
  const pendingSeekRef = useRef<number | null>(null)

  // Save playback progress every 5 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      if (playerRef.current && currentVideoId) {
        try {
          const time = playerRef.current.getCurrentTime()
          if (time > 0) saveProgress(currentVideoId, time)
        } catch {
          // Player may not be ready yet
        }
      }
    }, 5000)
    return () => clearInterval(interval)
  }, [currentVideoId])

  // Load a video — if player exists, load directly; otherwise just set state
  // and the player-creation effect below will handle it.
  // Automatically resumes from saved progress if no explicit startSeconds given.
  const loadVideo = useCallback((ytVideoId: string, startSeconds?: number) => {
    // Save progress of the current video before switching
    if (playerRef.current && currentVideoId && currentVideoId !== ytVideoId) {
      try {
        const time = playerRef.current.getCurrentTime()
        if (time > 0) saveProgress(currentVideoId, time)
      } catch {
        // Player may not be ready
      }
    }

    // Use saved progress if no explicit start time
    const resumeTime = startSeconds ?? getProgress(ytVideoId) ?? undefined

    setCurrentVideoId(ytVideoId)
    pendingSeekRef.current = resumeTime ?? null

    if (playerRef.current) {
      if (resumeTime && resumeTime > 0) {
        playerRef.current.loadVideoById({ videoId: ytVideoId, startSeconds: resumeTime })
      } else {
        playerRef.current.loadVideoById(ytVideoId)
      }
    }
    // If no player yet, the effect below creates it once the div is in the DOM
  }, [currentVideoId])

  // Create player when we have a video ID but no player yet (runs after render so div exists)
  useEffect(() => {
    if (!currentVideoId || playerRef.current || !playerContainerRef.current || !window.YT?.Player) return

    const startSeconds = pendingSeekRef.current
    pendingSeekRef.current = null

    playerRef.current = new window.YT.Player(playerContainerRef.current, {
      videoId: currentVideoId,
      playerVars: {
        autoplay: 1,
        enablejsapi: 1,
        modestbranding: 1,
        rel: 0,
        ...(startSeconds && startSeconds > 0 ? { start: Math.floor(startSeconds) } : {}),
      },
      events: {
        onStateChange: (event: { data: number }) => {
          if (event.data === window.YT.PlayerState.ENDED) {
            handleVideoEnded()
          }
        },
      },
    })
  }, [currentVideoId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-load first unwatched video when playlist changes, restoring saved progress
  useEffect(() => {
    if (!currentVideoId && videos.length > 0) {
      const firstActive = videos.find((v) => v.status === 'active')
      if (firstActive) {
        // loadVideo will automatically resume from saved progress if available
        loadVideo(firstActive.youtube_video_id)
      }
    }
  }, [videos, currentVideoId, loadVideo])

  const handleVideoEnded = async () => {
    // Mark current video as watched, then load next
    if (currentVideoId) clearProgress(currentVideoId)
    const currentVid = videos.find((v) => v.youtube_video_id === currentVideoId)
    if (currentVid && currentVid.status === 'active') {
      await markWatched.mutateAsync(currentVid.id)
    }
    advanceToNext()
  }

  const advanceToNext = () => {
    const currentIdx = videos.findIndex((v) => v.youtube_video_id === currentVideoId)
    const remaining = videos.filter(
      (v, i: number) => i > currentIdx && v.status === 'active'
    )
    if (remaining.length > 0) {
      loadVideo(remaining[0].youtube_video_id)
    } else {
      setCurrentVideoId(null)
      playerRef.current?.stopVideo()
    }
  }

  // Drag handlers
  const handleDragStart = (e: React.DragEvent, index: number) => {
    setDragIndex(index)
    dragNodeRef.current = e.currentTarget as HTMLDivElement
    e.dataTransfer.effectAllowed = 'move'
    requestAnimationFrame(() => {
      if (dragNodeRef.current) dragNodeRef.current.style.opacity = '0.4'
    })
  }

  const handleDragEnd = () => {
    if (dragNodeRef.current) dragNodeRef.current.style.opacity = '1'

    if (
      dragIndex !== null &&
      overIndex !== null &&
      dragIndex !== overIndex &&
      activePlaylistId
    ) {
      const activeVideos = videos.filter((v) => v.status === 'active')
      const reordered = [...activeVideos]
      const [moved] = reordered.splice(dragIndex, 1)
      reordered.splice(overIndex, 0, moved)
      reorderVideos.mutate({
        playlistId: activePlaylistId,
        videoIds: reordered.map((v) => v.id),
      })
    }

    setDragIndex(null)
    setOverIndex(null)
    dragNodeRef.current = null
  }

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setOverIndex(index)
  }

  const handlePlaylistChange = async (value: string) => {
    if (value === '__new__') {
      setShowNewPlaylist(true)
      return
    }
    setCurrentVideoId(null)
    playerRef.current?.stopVideo()
    await activatePlaylist.mutateAsync(value)
  }

  const handleCreatePlaylist = async () => {
    if (!newPlaylistName.trim()) return
    await createPlaylist.mutateAsync({ name: newPlaylistName.trim(), is_active: true })
    setNewPlaylistName('')
    setShowNewPlaylist(false)
    setCurrentVideoId(null)
  }

  const activeVideos = videos.filter((v) => v.status === 'active')
  const displayVideos = filterTab === 'active' ? activeVideos : videos

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto p-4 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Youtube className="h-5 w-5" />
            <h1 className="text-xl font-semibold">YouTube</h1>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setManageModalOpen(true)}>
                Manage Playlists
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Player */}
        <div className="aspect-video bg-black rounded-lg overflow-hidden">
          {currentVideoId ? (
            <div ref={playerContainerRef} className="w-full h-full" />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-white/50">
              <div className="text-center space-y-2">
                <Youtube className="h-12 w-12 mx-auto" />
                <p>Select a video to play</p>
              </div>
            </div>
          )}
        </div>

        {/* Now playing + Next button */}
        {currentVideo && (
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium truncate">
              Now playing: {currentVideo.title}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                handleVideoEnded()
              }}
              disabled={markWatched.isPending}
            >
              <SkipForward className="h-4 w-4 mr-1" />
              Next
            </Button>
          </div>
        )}

        {/* Playlist selector + Add Video */}
        <div className="flex items-center gap-2">
          {showNewPlaylist ? (
            <div className="flex gap-2 flex-1">
              <input
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
                placeholder="New playlist name"
                value={newPlaylistName}
                onChange={(e) => setNewPlaylistName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreatePlaylist()}
                autoFocus
              />
              <Button size="sm" onClick={handleCreatePlaylist}>Create</Button>
              <Button size="sm" variant="ghost" onClick={() => setShowNewPlaylist(false)}>Cancel</Button>
            </div>
          ) : (
            <Select
              value={activePlaylistId ?? ''}
              onValueChange={handlePlaylistChange}
            >
              <SelectTrigger className="w-64">
                <SelectValue placeholder="Select playlist" />
              </SelectTrigger>
              <SelectContent>
                {playlists.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
                <SelectItem value="__new__">+ New Playlist</SelectItem>
              </SelectContent>
            </Select>
          )}
        </div>

        {/* Filter tabs + Add Video */}
        <div className="flex items-center justify-between">
        <div className="flex gap-1 border rounded-lg p-1 w-fit">
          {(['active', 'watched', 'deleted', 'all'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setFilterTab(tab)}
              className={
                'px-3 py-1.5 text-sm rounded-md transition-colors ' +
                (filterTab === tab
                  ? 'bg-background shadow-sm font-medium'
                  : 'text-muted-foreground hover:text-foreground')
              }
            >
              {tab === 'active' ? 'Not Completed' : tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
          <Button onClick={() => setAddModalOpen(true)} size="sm">
            <Plus className="h-4 w-4 mr-1" />
            Add Video
          </Button>
        </div>

        {/* Video list */}
        <div className="space-y-1">
          {displayVideos.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No videos in this view.
            </p>
          ) : (
            displayVideos.map((video, index) => (
              <VideoRow
                key={video.id}
                video={video}
                index={index}
                isPlaying={video.youtube_video_id === currentVideoId}
                isDraggable={filterTab === 'active'}
                dragIndex={dragIndex}
                overIndex={overIndex}
                onPlay={() => loadVideo(video.youtube_video_id)}
                onMarkWatched={() => markWatched.mutate(video.id)}
                onMarkDeleted={() => markDeleted.mutate(video.id)}
                onRestore={() => restoreVideo.mutate(video.id)}
                onDragStart={handleDragStart}
                onDragEnd={handleDragEnd}
                onDragOver={handleDragOver}
              />
            ))
          )}
        </div>
      </div>

      <AddVideoModal
        open={addModalOpen}
        onOpenChange={setAddModalOpen}
        activePlaylistId={activePlaylistId}
      />

      <ManagePlaylistsModal
        open={manageModalOpen}
        onOpenChange={setManageModalOpen}
      />
    </div>
  )
}

// --- Video Row Component ---

interface VideoRowProps {
  video: YouTubeVideo
  index: number
  isPlaying: boolean
  isDraggable: boolean
  dragIndex: number | null
  overIndex: number | null
  onPlay: () => void
  onMarkWatched: () => void
  onMarkDeleted: () => void
  onRestore: () => void
  onDragStart: (e: React.DragEvent, index: number) => void
  onDragEnd: () => void
  onDragOver: (e: React.DragEvent, index: number) => void
}

function VideoRow({
  video,
  index,
  isPlaying,
  isDraggable,
  dragIndex,
  overIndex,
  onPlay,
  onMarkWatched,
  onMarkDeleted,
  onRestore,
  onDragStart,
  onDragEnd,
  onDragOver,
}: VideoRowProps) {
  const isOver = overIndex === index && dragIndex !== null && dragIndex !== index

  return (
    <div
      draggable={isDraggable}
      onDragStart={(e) => isDraggable && onDragStart(e, index)}
      onDragEnd={onDragEnd}
      onDragOver={(e) => isDraggable && onDragOver(e, index)}
      className={
        'flex items-center gap-2 rounded-md border px-3 py-2 transition-colors group' +
        (isOver ? ' border-primary bg-accent' : '') +
        (isPlaying ? ' bg-accent border-primary' : '') +
        (video.status === 'watched' ? ' opacity-60' : '') +
        (video.status === 'deleted' ? ' opacity-40' : '')
      }
    >
      {isDraggable && (
        <GripVertical className="h-4 w-4 shrink-0 text-muted-foreground cursor-grab active:cursor-grabbing" />
      )}

      {/* Thumbnail */}
      <div
        className="w-16 h-10 rounded overflow-hidden shrink-0 cursor-pointer relative group/thumb"
        onClick={onPlay}
      >
        {video.thumbnail_url ? (
          <img
            src={video.thumbnail_url}
            alt=""
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full bg-muted flex items-center justify-center">
            <Youtube className="h-4 w-4 text-muted-foreground" />
          </div>
        )}
      </div>

      {/* Title */}
      <span
        className="flex-1 text-sm font-medium truncate cursor-pointer"
        onClick={onPlay}
      >
        {video.title}
      </span>

      {/* Status badge */}
      {video.status !== 'active' && (
        <span className="text-xs text-muted-foreground capitalize shrink-0">
          {video.status}
        </span>
      )}

      {/* Actions */}
      <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        {video.status === 'active' && (
          <>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onMarkWatched} title="Mark watched">
              <Eye className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onMarkDeleted} title="Delete">
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </>
        )}
        {(video.status === 'watched' || video.status === 'deleted') && (
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onRestore} title="Restore">
            <RotateCcw className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </div>
  )
}
