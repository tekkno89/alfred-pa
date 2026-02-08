import { useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { LogOut, User, Brain, Settings, Bell, BellOff, Coffee } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuthStore } from '@/lib/auth'
import { useFocusStatus } from '@/hooks/useFocusMode'
import { apiGet } from '@/lib/api'
import type { SlackOAuthStatusResponse } from '@/types'

export function Header() {
  const navigate = useNavigate()
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)
  const { data: focusStatus } = useFocusStatus()

  const { data: oauthStatus } = useQuery({
    queryKey: ['slack-oauth-status'],
    queryFn: () => apiGet<SlackOAuthStatusResponse>('/auth/slack/oauth/status'),
  })

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const initials = user?.email
    ? user.email.substring(0, 2).toUpperCase()
    : 'U'

  const isInFocusMode = focusStatus?.is_active ?? false
  const hasSlackOAuth = oauthStatus?.connected ?? false
  const isPomodoro = focusStatus?.mode === 'pomodoro'
  const isPomodoroBreak = isPomodoro && focusStatus?.pomodoro_phase === 'break'

  // Determine button variant based on focus mode state
  const getFocusButtonVariant = () => {
    if (!isInFocusMode) return 'outline'
    if (isPomodoroBreak) return 'outline' // Will use custom yellow styling
    return 'destructive'
  }

  // Determine button styling for pomodoro break (yellow)
  const getFocusButtonClass = () => {
    const base = 'flex items-center gap-2'
    if (isPomodoroBreak) {
      return `${base} bg-yellow-500 hover:bg-yellow-600 text-white border-yellow-500`
    }
    return base
  }

  // Get the appropriate icon
  const getFocusIcon = () => {
    if (!isInFocusMode) return <Bell className="h-4 w-4" />
    if (isPomodoro) {
      if (isPomodoroBreak) return <Coffee className="h-4 w-4" />
      return <span className="text-base">🍅</span>
    }
    return <BellOff className="h-4 w-4" />
  }

  // Get the button label
  const getFocusLabel = () => {
    if (!isInFocusMode) return 'Focus Mode'
    if (isPomodoro) {
      if (isPomodoroBreak) return 'Break Time'
      return 'Pomodoro Active'
    }
    return 'Focus Mode Active'
  }

  return (
    <header className="h-14 border-b bg-background flex items-center justify-between px-4">
      <Link to="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
        <Brain className="h-6 w-6" />
        <span className="font-semibold text-lg">Alfred</span>
      </Link>

      <div className="flex items-center gap-2">
        {/* Focus Mode button - only show if Slack OAuth is connected */}
        {hasSlackOAuth && (
          <Button
            variant={getFocusButtonVariant()}
            size="sm"
            onClick={() => navigate('/focus')}
            className={getFocusButtonClass()}
          >
            {getFocusIcon()}
            <span>{getFocusLabel()}</span>
          </Button>
        )}

        {/* User dropdown */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="relative h-9 w-9 rounded-full">
              <Avatar className="h-9 w-9">
                <AvatarFallback>{initials}</AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>
              <div className="flex flex-col space-y-1">
                <p className="text-sm font-medium">{user?.email}</p>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate('/memories')}>
              <User className="mr-2 h-4 w-4" />
              Memories
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => navigate('/settings')}>
              <Settings className="mr-2 h-4 w-4" />
              Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleLogout}>
              <LogOut className="mr-2 h-4 w-4" />
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
