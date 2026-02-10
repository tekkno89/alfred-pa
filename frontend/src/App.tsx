import { Routes, Route } from 'react-router-dom'
import { LoginPage } from '@/pages/LoginPage'
import { RegisterPage } from '@/pages/RegisterPage'
import { HomePage } from '@/pages/HomePage'
import { ChatPage } from '@/pages/ChatPage'
import { MemoriesPage } from '@/pages/MemoriesPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { SessionsPage } from '@/pages/SessionsPage'
import { FocusPage } from '@/pages/FocusPage'
import { FocusSettingsPage } from '@/pages/FocusSettingsPage'
import { WebhooksPage } from '@/pages/WebhooksPage'
import { AppLayout } from '@/components/layout/AppLayout'
import { AuthGuard } from '@/components/auth/AuthGuard'
import { NotificationProvider } from '@/components/notifications/NotificationProvider'
import { NotificationBanner } from '@/components/notifications/NotificationBanner'

function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* Protected routes */}
        <Route
          element={
            <AuthGuard>
              <NotificationProvider>
                <NotificationBanner />
                <AppLayout />
              </NotificationProvider>
            </AuthGuard>
          }
        >
          <Route path="/" element={<HomePage />} />
          <Route path="/chat/:sessionId" element={<ChatPage />} />
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/memories" element={<MemoriesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/focus" element={<FocusPage />} />
          <Route path="/settings/focus" element={<FocusSettingsPage />} />
          <Route path="/settings/webhooks" element={<WebhooksPage />} />
        </Route>
      </Routes>
    </div>
  )
}

export default App
