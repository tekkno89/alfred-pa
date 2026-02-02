import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/lib/auth'

interface AuthGuardProps {
  children: React.ReactNode
}

export function AuthGuard({ children }: AuthGuardProps) {
  const token = useAuthStore((state) => state.token)
  const location = useLocation()

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <>{children}</>
}
