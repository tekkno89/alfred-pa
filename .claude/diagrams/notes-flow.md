# Notes System

## Overview

Markdown-based note-taking with auto-save, local draft persistence, tagging, favorites, and archive. The frontend editor provides a live preview with offline resilience.

## Architecture

```mermaid
flowchart TD
    subgraph "Frontend"
        EDITOR[NoteEditorPage<br/>Markdown editor + preview]
        LIST[NotesPage<br/>List with filters]
        CARD[NotesCard<br/>Dashboard widget]
        DRAFT[useLocalDraft<br/>localStorage backup]
        AUTOSAVE[Auto-save<br/>750ms debounce]
    end

    subgraph "Backend"
        API[REST API<br/>/notes endpoints]
        REPO[NoteRepository<br/>CRUD + filtering]
    end

    subgraph "Storage"
        DB[(PostgreSQL)]
        LOCAL[(localStorage<br/>draft backup)]
    end

    EDITOR --> AUTOSAVE
    AUTOSAVE --> API
    EDITOR --> DRAFT
    DRAFT --> LOCAL
    LIST --> API
    CARD --> API
    API --> REPO
    REPO --> DB
```

## Auto-Save Flow

```mermaid
sequenceDiagram
    participant User as User
    participant Editor as NoteEditorPage
    participant Draft as localStorage
    participant API as Backend API

    User->>Editor: Type content
    Editor->>Draft: Save local draft (immediate)

    Note over Editor: 750ms debounce timer

    Editor->>API: PATCH /notes/{id}
    alt Online + Success
        API-->>Editor: 200 OK
        Editor->>Draft: Clear local draft
        Editor->>Editor: Show "Saved" indicator
    else Offline
        Editor->>Editor: Show "Offline" indicator
        Editor->>Editor: Queue for retry
    else API Error
        Editor->>Editor: Show "Error" indicator
        Editor->>Editor: Retry with backoff (2s, 5s, 10s)
    end

    Note over User,API: On page blur / tab switch
    Editor->>API: Flush pending save
```

## Data Model

```mermaid
erDiagram
    User ||--o{ Note : "has"

    Note {
        uuid id PK
        uuid user_id FK
        string title
        text body "Markdown content"
        boolean is_favorited
        boolean is_archived
        array tags "string[]"
        datetime created_at
        datetime updated_at
    }
```

## Frontend Features

- **Markdown editor** with tab indentation support
- **Live preview** toggle (edit / preview / split)
- **Auto-save** with 750ms debounce and save status indicator
- **Local draft persistence** with recovery dialog on page load
- **Keyboard shortcuts**: Cmd/Ctrl+S for manual save
- **Offline detection** with retry mechanism (exponential backoff)
- **Focus loss flush** — saves immediately when tab loses focus
- **Tags** for organization
- **Favorites** and **archive** for note management

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/notes` | List notes with pagination, sort, archived filter |
| POST | `/notes` | Create note |
| GET | `/notes/{id}` | Get single note |
| PATCH | `/notes/{id}` | Update note |
| POST | `/notes/{id}/archive` | Archive note |
| POST | `/notes/{id}/restore` | Restore archived note |
| DELETE | `/notes/{id}` | Delete note permanently |

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/api/notes.py` | REST API endpoints |
| `backend/app/db/models/note.py` | SQLAlchemy model |
| `backend/app/db/repositories/note.py` | Data access layer |
| `backend/app/schemas/note.py` | Pydantic schemas |
| `frontend/src/pages/NotesPage.tsx` | Note list with filters |
| `frontend/src/pages/NoteEditorPage.tsx` | Markdown editor with auto-save |
| `frontend/src/hooks/useNotes.ts` | React Query hooks |
| `frontend/src/hooks/useLocalDraft.ts` | localStorage draft persistence |
| `frontend/src/hooks/useMarkdownEditor.ts` | Tab indentation support |
| `frontend/src/hooks/useSaveOnFocusLoss.ts` | Flush save on blur |
| `frontend/src/hooks/useOnlineStatus.ts` | Online/offline detection |
| `frontend/src/components/dashboard/NotesCard.tsx` | Dashboard widget |

## Status

✅ Complete
