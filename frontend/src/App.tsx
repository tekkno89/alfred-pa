import { Routes, Route } from 'react-router-dom'
import { LoginPage } from '@/pages/LoginPage'
import { RegisterPage } from '@/pages/RegisterPage'
import { HomePage } from '@/pages/HomePage'
import { ChatPage } from '@/pages/ChatPage'
import { MemoriesPage } from '@/pages/MemoriesPage'
import { AppLayout } from '@/components/layout/AppLayout'
import { AuthGuard } from '@/components/auth/AuthGuard'

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
              <AppLayout />
            </AuthGuard>
          }
        >
          <Route path="/" element={<HomePage />} />
          <Route path="/chat/:sessionId" element={<ChatPage />} />
          <Route path="/memories" element={<MemoriesPage />} />
        </Route>
      </Routes>
    </div>
  )
}

export default App
