# YouTube Integration

## Overview

YouTube watch queue management with playlist support, oEmbed metadata extraction, and an embedded player with progress tracking. Videos are added by URL and organized into playlists.

## Architecture

```mermaid
flowchart TD
    subgraph "Entry Points"
        TOOL[manage_youtube Tool<br/>LLM agent action]
        API[REST API<br/>/youtube endpoints]
        UI[YouTubePage<br/>Add Video modal]
    end

    subgraph "Backend"
        SVC[YouTubeService<br/>metadata extraction]
        REPO[YouTubeRepository<br/>playlist + video CRUD]
        OEMBED[YouTube oEmbed API<br/>title, thumbnail]
    end

    subgraph "Storage"
        DB[(PostgreSQL<br/>playlists + videos)]
    end

    TOOL --> REPO
    TOOL --> SVC
    API --> REPO
    API --> SVC
    UI --> API

    SVC --> OEMBED
    REPO --> DB
```

## Video Add Flow

```mermaid
sequenceDiagram
    participant User as User / LLM
    participant API as Backend
    participant YT as YouTubeService
    participant oEmbed as YouTube oEmbed API
    participant DB as PostgreSQL

    User->>API: Add video (URL)
    API->>YT: extract_video_id(url)
    YT-->>API: video_id (e.g. "dQw4w9WgXcQ")
    API->>YT: fetch_metadata(url)
    YT->>oEmbed: GET oembed?url=...
    oEmbed-->>YT: {title, thumbnail_url}
    YT-->>API: metadata
    API->>DB: Create YouTubeVideo
    Note over DB: playlist_id, youtube_url,<br/>youtube_video_id, title,<br/>thumbnail_url, sort_order
    API-->>User: Video added
```

## URL Format Support

| Format | Example |
|--------|---------|
| Standard | `https://www.youtube.com/watch?v=VIDEO_ID` |
| Short | `https://youtu.be/VIDEO_ID` |
| Embed | `https://www.youtube.com/embed/VIDEO_ID` |
| Shorts | `https://youtube.com/shorts/VIDEO_ID` |

## Data Model

```mermaid
erDiagram
    User ||--o{ YouTubePlaylist : "has"
    YouTubePlaylist ||--o{ YouTubeVideo : "contains"

    YouTubePlaylist {
        uuid id PK
        uuid user_id FK
        string name
        boolean is_active
        boolean is_archived
    }
    YouTubeVideo {
        uuid id PK
        uuid playlist_id FK
        uuid user_id FK
        string youtube_url
        string youtube_video_id
        string title
        string thumbnail_url
        string status "active | watched"
        int sort_order
    }
```

## Frontend Features

- **Embedded player** via YouTube IFrame API with progress tracking (localStorage)
- **Drag-and-drop** video reordering within playlists
- **Active playlist** concept — default target for new videos
- **Video filters**: active, watched, deleted, all
- **Playback resume** from saved progress on page reload
- **Next/Skip** controls for queue navigation

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/youtube/playlists` | List all playlists |
| POST | `/youtube/playlists` | Create playlist |
| PATCH | `/youtube/playlists/{id}` | Update playlist |
| DELETE | `/youtube/playlists/{id}` | Delete playlist |
| POST | `/youtube/playlists/{id}/activate` | Set as active playlist |
| GET | `/youtube/playlists/{id}/videos` | List videos in playlist |
| POST | `/youtube/videos` | Add video to playlist |
| PATCH | `/youtube/videos/{id}` | Update video (status, order) |
| DELETE | `/youtube/videos/{id}` | Delete video |
| POST | `/youtube/videos/reorder` | Reorder videos in playlist |
| GET | `/youtube/metadata` | Fetch oEmbed metadata for URL |

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/tools/youtube.py` | `ManageYouTubeTool` — agent tool |
| `backend/app/api/youtube.py` | REST API endpoints |
| `backend/app/db/models/youtube.py` | SQLAlchemy models (Playlist + Video) |
| `backend/app/db/repositories/youtube.py` | Data access layer |
| `backend/app/schemas/youtube.py` | Pydantic schemas |
| `backend/app/services/youtube.py` | oEmbed metadata + video ID extraction |
| `frontend/src/pages/YouTubePage.tsx` | Player, playlists, drag-and-drop |
| `frontend/src/hooks/useYouTube.ts` | React Query hooks |
| `frontend/src/components/dashboard/YouTubeCard.tsx` | Dashboard widget |

## Status

✅ Complete
