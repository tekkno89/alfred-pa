# Frontend Architecture

## Component Hierarchy

```mermaid
graph TD
    App[App.tsx] --> PublicRoutes[Public Routes]
    App --> ProtectedRoutes[Protected Routes]

    PublicRoutes --> LoginPage[LoginPage]
    PublicRoutes --> RegisterPage[RegisterPage]
    LoginPage --> LoginForm[LoginForm]
    RegisterPage --> RegisterForm[RegisterForm]

    ProtectedRoutes --> AuthGuard[AuthGuard]
    AuthGuard --> AppLayout[AppLayout]

    AppLayout --> Header[Header]
    AppLayout --> Sidebar[Sidebar]
    AppLayout --> MainContent[Main Content]

    Header --> UserDropdown[User Dropdown]
    Sidebar --> SessionList[SessionList]
    SessionList --> SessionItem[SessionItem]

    MainContent --> HomePage[HomePage]
    MainContent --> ChatPage[ChatPage]
    MainContent --> MemoriesPage[MemoriesPage]
    MainContent --> BartPage[BartPage]
    MainContent --> AdminPage[AdminPage]
    MainContent --> FocusPage[FocusPage]
    MainContent --> FocusSettingsPage[FocusSettingsPage]
    MainContent --> WebhooksPage[WebhooksPage]

    HomePage --> BartCard[BartCard]
    BartPage --> BartStationPicker[BartStationPicker]
    BartPage --> StationBoard[StationBoard]

    ChatPage --> ChatContainer[ChatContainer]
    ChatContainer --> MessageList[MessageList]
    ChatContainer --> ChatInput[ChatInput]
    MessageList --> MessageBubble[MessageBubble]
    MessageList --> StreamingBubble[StreamingBubble]

    MemoriesPage --> MemoryForm[MemoryForm]
    MemoriesPage --> MemoryList[MemoryList]
    MemoryList --> MemoryItem[MemoryItem]
```

## Data Flow

```mermaid
flowchart LR
    subgraph Frontend
        Components[React Components]
        Hooks[Custom Hooks]
        Store[Zustand Store]
        RQ[React Query]
    end

    subgraph Backend
        API[FastAPI /api]
    end

    Components --> Hooks
    Hooks --> RQ
    Hooks --> Store
    RQ --> API
    Store --> |Auth Token| RQ
    API --> |JSON/SSE| RQ
    RQ --> |Cache| Components
```

## State Management

```mermaid
flowchart TD
    subgraph "Zustand (Client State)"
        AuthStore[Auth Store]
        AuthStore --> Token[JWT Token]
        AuthStore --> User[User Info]
    end

    subgraph "React Query (Server State)"
        Sessions[Sessions Query]
        Session[Session + Messages]
        Memories[Memories Query]
        Dashboard[Dashboard Queries]
        FocusQueries[Focus Queries]
        Dashboard --> AvailableCards[Available Cards]
        Dashboard --> BartDepartures[BART Departures]
        Dashboard --> DashboardPrefs[Dashboard Preferences]
        FocusQueries --> FocusStatus[Focus Status]
        FocusQueries --> FocusSettings[Focus Settings]
    end

    subgraph "Local State"
        StreamingContent[Streaming Content]
        IsStreaming[Is Streaming]
        FormInputs[Form Inputs]
    end
```

## SSE Streaming Flow

```mermaid
sequenceDiagram
    participant UI as ChatInput
    participant Hook as useChat
    participant API as Backend API
    participant LLM as LLM Provider

    UI->>Hook: sendMessage(content)
    Hook->>Hook: Add user message to cache
    Hook->>API: POST /sessions/{id}/messages
    API->>LLM: Generate response

    loop Streaming
        LLM-->>API: Token
        API-->>Hook: SSE: {type: "token", content: "..."}
        Hook->>Hook: Accumulate streamingContent
        Hook-->>UI: Re-render with partial response
    end

    API-->>Hook: SSE: {type: "done"}
    Hook->>Hook: Add assistant message to cache
    Hook->>Hook: Clear streamingContent
```

## Key Files

| Category | Files |
|----------|-------|
| **Entry** | `main.tsx`, `App.tsx` |
| **Lib** | `lib/api.ts`, `lib/auth.ts`, `lib/sse.ts` |
| **Hooks** | `hooks/useSessions.ts`, `hooks/useChat.ts`, `hooks/useMemories.ts`, `hooks/useDashboard.ts`, `hooks/useAdmin.ts`, `hooks/useFocusMode.ts`, `hooks/useNotifications.ts`, `hooks/useAlertSound.ts`, `hooks/useTitleFlash.ts` |
| **Pages** | `pages/LoginPage.tsx`, `pages/ChatPage.tsx`, `pages/MemoriesPage.tsx`, `pages/BartPage.tsx`, `pages/AdminPage.tsx`, `pages/FocusPage.tsx`, `pages/FocusSettingsPage.tsx`, `pages/WebhooksPage.tsx` |
| **Dashboard** | `components/dashboard/BartCard.tsx`, `BartStationPicker.tsx`, `sortEstimates.ts` |
| **Layout** | `components/layout/AppLayout.tsx`, `Sidebar.tsx`, `Header.tsx` |
| **Focus** | `components/focus/FocusToggle.tsx`, `PomodoroTimer.tsx`, `VipList.tsx` |
| **Notifications** | `components/notifications/NotificationProvider.tsx` (SSE events, sound loop, title flash), `NotificationBanner.tsx` (bypass alert banner with animation) |
| **UI** | `components/ui/*.tsx` (shadcn/ui: button, input, card, select, switch, etc.) |

## Technology Stack

- **Framework**: React 18 + TypeScript
- **Build**: Vite
- **Routing**: React Router v6
- **Server State**: TanStack React Query
- **Client State**: Zustand (persisted to localStorage)
- **Styling**: Tailwind CSS + shadcn/ui patterns
- **Testing**: Vitest + React Testing Library
