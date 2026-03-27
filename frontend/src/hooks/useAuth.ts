/**
 * 认证 Hook：login / logout / refreshToken（App 初始化时静默续期）。
 *
 * 依赖：useAuthStore（内存 Token）+ authApi（网络请求）
 */
import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '@/lib/api'
import { useAuthStore } from '@/store/useAuthStore'

export function useAuth() {
  const navigate = useNavigate()
  const { setTokens, clearAuth } = useAuthStore()

  /** 登录：写入 Token → 跳转仪表盘 */
  const login = useCallback(
    async (username: string, password: string) => {
      const data = await authApi.login({ username, password })
      setTokens(data.access_token, data.user)
      navigate('/', { replace: true })
    },
    [setTokens, navigate]
  )

  /** 登出：清除内存 Token，通知后端使 Cookie 失效 */
  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } catch {
      // 忽略错误，强制清除本地状态
    } finally {
      clearAuth()
      navigate('/login', { replace: true })
    }
  }, [clearAuth, navigate])

  /**
   * 静默刷新：用 HttpOnly Cookie 中的 refresh_token 换取新 access_token。
   * 返回 true 表示刷新成功，false 表示失败（用户需要重新登录）。
   * 在以下场景调用：
   *   1. App 初始化（页面刷新后恢复登录状态）
   *   2. WebSocket 收到 4401 关闭码
   */
  const refreshToken = useCallback(async (): Promise<boolean> => {
    try {
      const data = await authApi.refresh()
      setTokens(data.access_token, data.user)
      return true
    } catch {
      clearAuth()
      return false
    }
  }, [setTokens, clearAuth])

  return { login, logout, refreshToken }
}
