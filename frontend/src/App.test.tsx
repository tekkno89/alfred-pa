import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, beforeEach } from 'vitest'
import App from './App'
import { useAuthStore } from './lib/auth'

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })
}

function renderApp(initialRoute = '/') {
  const queryClient = createQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('App', () => {
  beforeEach(() => {
    // Reset auth store before each test
    useAuthStore.getState().logout()
  })

  describe('unauthenticated', () => {
    it('redirects to login page when not authenticated', () => {
      renderApp('/')
      expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
      expect(screen.getByText('Enter your credentials to access Alfred')).toBeInTheDocument()
    })

    it('shows register page', () => {
      renderApp('/register')
      expect(screen.getByRole('heading', { name: 'Create account' })).toBeInTheDocument()
      expect(screen.getByText('Sign up to start using Alfred')).toBeInTheDocument()
    })

    it('has link to register from login', () => {
      renderApp('/login')
      expect(screen.getByRole('link', { name: 'Create one' })).toBeInTheDocument()
    })

    it('has link to login from register', () => {
      renderApp('/register')
      expect(screen.getByRole('link', { name: 'Sign in' })).toBeInTheDocument()
    })
  })

  describe('authenticated', () => {
    beforeEach(() => {
      // Mock authenticated state
      useAuthStore.getState().setAuth('test-token', {
        id: 'test-user-id',
        email: 'test@example.com',
        created_at: new Date().toISOString(),
      })
    })

    it('shows home page when authenticated', () => {
      renderApp('/')
      expect(screen.getByText('Welcome to Alfred')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'New Conversation' })).toBeInTheDocument()
    })
  })
})
