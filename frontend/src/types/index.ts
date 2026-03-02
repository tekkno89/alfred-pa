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
  role: 'admin' | 'user'
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
  is_starred?: boolean
}

export interface Session {
  id: string
  title: string | null
  source: 'webapp' | 'slack'
  slack_channel_id: string | null
  slack_thread_ts: string | null
  is_starred: boolean
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

export interface ToolSource {
  title: string
  url: string
}

export interface ToolResultData {
  query: string
  sources: ToolSource[]
}

export interface StreamEvent {
  type: 'token' | 'tool_use' | 'tool_result' | 'done' | 'error'
  content?: string
  message_id?: string
  tool_name?: string
  tool_args?: Record<string, unknown>
  tool_data?: ToolResultData
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

// Notes
export interface NoteCreate {
  title?: string
  body?: string
  is_favorited?: boolean
  tags?: string[]
}

export interface NoteUpdate {
  title?: string | null
  body?: string | null
  is_favorited?: boolean | null
  tags?: string[] | null
}

export interface Note {
  id: string
  title: string
  body: string
  is_favorited: boolean
  is_archived: boolean
  tags: string[]
  created_at: string
  updated_at: string
}

export interface NoteList {
  items: Note[]
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

// Focus Mode
export interface FocusEnableRequest {
  duration_minutes?: number | null
  custom_message?: string | null
}

export interface FocusStatusResponse {
  is_active: boolean
  mode: 'simple' | 'pomodoro'
  started_at?: string | null
  ends_at?: string | null
  custom_message?: string | null
  pomodoro_phase?: 'work' | 'break' | null
  pomodoro_session_count: number
  pomodoro_total_sessions?: number | null
  pomodoro_work_minutes?: number | null
  pomodoro_break_minutes?: number | null
  time_remaining_seconds?: number | null
}

export interface PomodoroStartRequest {
  custom_message?: string | null
  work_minutes?: number | null
  break_minutes?: number | null
  total_sessions?: number | null
}

export interface BypassNotificationConfig {
  alfred_ui_enabled: boolean
  email_enabled: boolean
  email_address?: string | null
  sms_enabled: boolean
  phone_number?: string | null
  alert_sound_enabled: boolean
  alert_sound_name: string
  alert_title_flash_enabled: boolean
}

export interface FocusSettingsResponse {
  default_message?: string | null
  pomodoro_work_minutes: number
  pomodoro_break_minutes: number
  bypass_notification_config?: BypassNotificationConfig | null
  slack_status_text: string
  slack_status_emoji: string
  pomodoro_work_status_text: string
  pomodoro_work_status_emoji: string
  pomodoro_break_status_text: string
  pomodoro_break_status_emoji: string
}

export interface FocusSettingsUpdate {
  default_message?: string | null
  pomodoro_work_minutes?: number | null
  pomodoro_break_minutes?: number | null
  bypass_notification_config?: BypassNotificationConfig | null
  slack_status_text?: string | null
  slack_status_emoji?: string | null
  pomodoro_work_status_text?: string | null
  pomodoro_work_status_emoji?: string | null
  pomodoro_break_status_text?: string | null
  pomodoro_break_status_emoji?: string | null
}

export interface VIPResponse {
  id: string
  slack_user_id: string
  display_name?: string | null
  created_at: string
}

export interface VIPListResponse {
  vips: VIPResponse[]
}

export interface VIPAddRequest {
  slack_user_id: string
  display_name?: string | null
}

// Webhooks
export type WebhookEventType =
  | 'focus_started'
  | 'focus_ended'
  | 'focus_bypass'
  | 'pomodoro_work_started'
  | 'pomodoro_break_started'

export interface WebhookCreateRequest {
  name: string
  url: string
  event_types: WebhookEventType[]
}

export interface WebhookUpdateRequest {
  name?: string | null
  url?: string | null
  enabled?: boolean | null
  event_types?: WebhookEventType[] | null
}

export interface WebhookResponse {
  id: string
  name: string
  url: string
  enabled: boolean
  event_types: WebhookEventType[]
  created_at: string
  updated_at: string
}

export interface WebhookListResponse {
  webhooks: WebhookResponse[]
}

export interface WebhookTestResponse {
  success: boolean
  status_code?: number | null
  error?: string | null
}

// Slack OAuth
export interface SlackOAuthStatusResponse {
  connected: boolean
  scope?: string | null
}

// Notification Events
export interface NotificationEvent {
  type: string
  timestamp: string
  sender_slack_id?: string
  sender_name?: string
  message?: string
  [key: string]: unknown
}

// Dashboard / BART
export interface BartStationPreference {
  abbr: string
  platform: number | null
  sort?: 'destination' | 'eta'
  destinations?: string[]
}

export interface BartEstimate {
  destination: string
  abbreviation: string
  minutes: string
  platform: string
  direction: string
  color: string
  hex_color: string
  length: string
  delay: string
}

export interface BartDepartureResponse {
  station_name: string
  station_abbr: string
  estimates: BartEstimate[]
  fetched_at: string
}

export interface BartStation {
  name: string
  abbr: string
  city: string
  county: string
  latitude: number
  longitude: number
}

export interface BartStationsResponse {
  stations: BartStation[]
}

export interface DashboardPreference {
  id: string
  card_type: string
  preferences: Record<string, unknown>
  sort_order: number
  created_at: string
  updated_at: string
}

export interface DashboardPreferenceList {
  items: DashboardPreference[]
}

export interface DashboardPreferenceUpdate {
  preferences: Record<string, unknown>
  sort_order?: number
}

export interface FeatureAccess {
  id: string
  user_id: string
  feature_key: string
  enabled: boolean
  granted_by: string | null
  created_at: string
  updated_at: string
}

export interface AdminUser {
  id: string
  email: string
  role: 'admin' | 'user'
  created_at: string
}

export interface AdminUserList {
  items: AdminUser[]
}

export interface RoleUpdate {
  role: 'admin' | 'user'
}

export interface FeatureAccessUpdate {
  enabled: boolean
}

export interface SystemSetting {
  key: string
  value: string
}

export interface SystemSettingUpdate {
  value: string
}

// GitHub Integration
export interface GitHubConnection {
  id: string
  provider: string
  account_label: string
  external_account_id: string | null
  token_type: string
  scope: string | null
  expires_at: string | null
  created_at: string
  app_config_id: string | null
  app_config_label: string | null
}

export interface GitHubConnectionList {
  connections: GitHubConnection[]
}

export interface GitHubPATRequest {
  token: string
  account_label: string
}

export interface GitHubAppConfig {
  id: string
  label: string
  client_id: string
  github_app_id: string | null
  created_at: string
}

export interface GitHubAppConfigList {
  configs: GitHubAppConfig[]
}

export interface GitHubAppConfigCreateRequest {
  label: string
  client_id: string
  client_secret: string
  github_app_id?: string | null
}
