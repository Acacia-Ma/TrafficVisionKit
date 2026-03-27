import { create } from 'zustand'
import type { UserInfo } from '@/types/api'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: UserInfo | null
  isAuthenticated: boolean
  setTokens: (accessToken: string, refreshToken: string | null, user: UserInfo) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  refreshToken: null,
  user: null,
  isAuthenticated: false,

  setTokens: (accessToken, refreshToken, user) => {
    // 保存 refresh token 到 localStorage 作为备选方案
    if (refreshToken) {
      localStorage.setItem('refresh_token_backup', refreshToken)
    }
    set({ accessToken, refreshToken, user, isAuthenticated: true })
  },

  clearAuth: () => {
    localStorage.removeItem('refresh_token_backup')
    set({ accessToken: null, refreshToken: null, user: null, isAuthenticated: false })
  },
}))
