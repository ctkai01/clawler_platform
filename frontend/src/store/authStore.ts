import { create } from 'zustand'
import type { SessionUser } from '@/types/auth'
import { setToken } from '@/lib/apiClient'

interface AuthState {
  user: SessionUser | null
  isBootstrapping: boolean
  setUser: (user: SessionUser | null) => void
  setBootstrapping: (v: boolean) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  // true until the app has tried to resolve an existing token into a user
  // (via GET /auth/me) — guards must not redirect to /login while this is
  // true, or a page refresh would bounce a logged-in user out.
  isBootstrapping: true,
  setUser: (user) => set({ user }),
  setBootstrapping: (v) => set({ isBootstrapping: v }),
  logout: () => {
    setToken(null)
    set({ user: null })
  },
}))
