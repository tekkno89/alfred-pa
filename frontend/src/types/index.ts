// API Types matching backend schemas

// Auth
export interface UserRegister {
  email: string
  password: string
}

export interface UserLogin {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface User {
  id: string
  email: string
  slack_user_id?: string | null
  created_at: string
}

// Slack Linking
export interface SlackLinkRequest {
  code: string
}

export interface SlackStatusResponse {
  linked: boolean
  slack_user_id?: string | null
}

// Sessions
export interface SessionCreate {
  title?: string
}

export interface SessionUpdate {
  title?: string
}

export interface Session {
  id: string
  title: string | null
  source: 'webapp' | 'slack'
  slack_channel_id: string | null
  slack_thread_ts: string | null
  created_at: string
  updated_at: string
}

export interface SessionWithMessages extends Session {
  messages: Message[]
}

export interface SessionList {
  items: Session[]
  total: number
  page: number
  size: number
}

// Messages
export interface MessageCreate {
  content: string
}

export interface Message {
  id: string
  session_id: string
  role: 'user' | 'assistant'
  content: string
  metadata_: Record<string, unknown> | null
  created_at: string
}

export interface MessageList {
  items: Message[]
  total: number
}

export interface StreamEvent {
  type: 'token' | 'done' | 'error'
  content?: string
  message_id?: string
}

// Memories
export type MemoryType = 'preference' | 'knowledge' | 'summary'

export interface MemoryCreate {
  type: MemoryType
  content: string
}

export interface MemoryUpdate {
  content: string
}

export interface Memory {
  id: string
  type: MemoryType
  content: string
  source_session_id: string | null
  created_at: string
  updated_at: string
}

export interface MemoryList {
  items: Memory[]
  total: number
  page: number
  size: number
}

// Common
export interface DeleteResponse {
  success: boolean
}

export interface ApiError {
  detail: string
}
