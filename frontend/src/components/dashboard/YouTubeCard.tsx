import { useNavigate } from 'react-router-dom'
import { Youtube, Play, Plus } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { useYouTubeDashboard } from '@/hooks/useYouTube'

export function YouTubeCard() {
  const navigate = useNavigate()
  const { data, isLoading } = useYouTubeDashboard()

  return (
    <Card
      className="cursor-pointer hover:shadow-md transition-shadow relative h-full flex flex-col"
      onClick={() => navigate('/youtube')}
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Youtube className="h-4 w-4" />
          YouTube
          {data?.playlist_name && (
            <span className="text-xs font-normal text-muted-foreground ml-auto">
              {data.playlist_name} ({data.active_video_count})
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 flex items-center justify-center">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : data?.current_video ? (
          <div className="w-full">
            <div className="relative group">
              {data.current_video.thumbnail_url ? (
                <img
                  src={data.current_video.thumbnail_url}
                  alt={data.current_video.title}
                  className="w-full rounded-md object-cover aspect-video"
                />
              ) : (
                <div className="w-full rounded-md bg-muted aspect-video flex items-center justify-center">
                  <Youtube className="h-8 w-8 text-muted-foreground" />
                </div>
              )}
              <div className="absolute inset-0 bg-black/30 rounded-md flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                <Play className="h-10 w-10 text-white fill-white" />
              </div>
            </div>
            <p className="text-sm font-medium mt-2 line-clamp-2">{data.current_video.title}</p>
          </div>
        ) : (
          <div className="text-center space-y-2">
            <Youtube className="h-8 w-8 mx-auto text-muted-foreground" />
            <p className="text-sm text-muted-foreground">No videos queued</p>
          </div>
        )}
      </CardContent>
      <button
        className="absolute bottom-3 right-3 h-8 w-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-sm hover:bg-primary/90 transition-colors"
        onClick={(e) => {
          e.stopPropagation()
          navigate('/youtube?add=true')
        }}
      >
        <Plus className="h-6 w-6 stroke-[2.5]" />
      </button>
    </Card>
  )
}
