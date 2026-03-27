import { create } from 'zustand'
import type { UserInfo } from '@/types/api'

interface AuthState {
  accessToken: string | null
  user: UserInfo | null
  isAuthenticated: boolean
  setTokens: (token: string, user: UserInfo) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  isAuthenticated: false,

  setTokens: (token, user) =>
    set({ accessToken: token, user, isAuthenticated: true }),

  clearAuth: () =>
    set({ accessToken: null, user: null, isAuthenticated: false }),
}))
