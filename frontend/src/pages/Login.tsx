import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/store/useAuthStore'

// 从 axios 错误中提取状态码
function getErrorStatus(err: unknown): number | null {
  if (err && typeof err === 'object' && 'response' in err) {
    const r = (err as { response?: { status?: number } }).response
    return r?.status ?? null
  }
  return null
}

function getErrorData(err: unknown): { message?: string; locked_until?: string } {
  if (err && typeof err === 'object' && 'response' in err) {
    const r = (err as { response?: { data?: unknown } }).response
    if (r?.data && typeof r.data === 'object') return r.data as { message?: string; locked_until?: string }
  }
  return {}
}

// 将 ISO 时间戳换算为剩余分钟数
function minutesUntil(iso: string): number {
  const diff = new Date(iso).getTime() - Date.now()
  return Math.max(0, Math.ceil(diff / 60_000))
}

export default function Login() {
  const { login, refreshToken } = useAuth()
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [initDone, setInitDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lockMinutes, setLockMinutes] = useState<number | null>(null)

  const usernameRef = useRef<HTMLInputElement>(null)
  const hasInitialized = useRef(false)

  // App 初始化时静默刷新 Token（页面刷新后恢复登录状态）
  useEffect(() => {
    if (hasInitialized.current) return
    hasInitialized.current = true
    
    console.log('[Login] Starting initialization: attempting token refresh')
    refreshToken()
      .then((ok) => {
        console.log(`[Login] Token refresh result: ${ok ? 'success' : 'failed'}`)
        if (ok) {
          console.log('[Login] Redirecting to dashboard')
          navigate(from, { replace: true })
        }
      })
      .finally(() => {
        console.log('[Login] Initialization complete')
        setInitDone(true)
      })
  // 仅执行一次
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 若已登录（刷新成功），跳转
  useEffect(() => {
    if (isAuthenticated && initDone) {
      navigate(from, { replace: true })
    }
  // 仅在 isAuthenticated 从 false 变为 true 时执行一次
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated])

  useEffect(() => {
    if (initDone) usernameRef.current?.focus()
  }, [initDone])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLockMinutes(null)
    if (!username.trim() || !password) {
      setError('请输入用户名和密码')
      return
    }

    setLoading(true)
    try {
      await login(username.trim(), password)
    } catch (err) {
      const status = getErrorStatus(err)
      const data = getErrorData(err)

      if (status === 423) {
        const mins = data.locked_until ? minutesUntil(data.locked_until) : 0
        setLockMinutes(mins)
        setError(
          mins > 0
            ? `账号已被锁定，请 ${mins} 分钟后再试`
            : '账号已被锁定，请联系管理员'
        )
      } else if (status === 401) {
        setError('用户名或密码错误')
      } else {
        setError(data.message ?? '登录失败，请检查网络后重试')
      }
    } finally {
      setLoading(false)
    }
  }

  if (!initDone) {
    return (
      <div className="flex h-full items-center justify-center bg-bg-base">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </div>
    )
  }

  return (
    <div className="relative flex h-full flex-col items-center justify-center overflow-hidden bg-bg-base px-4">
      {/* 扫描线动画 */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,212,255,0.015) 2px, rgba(0,212,255,0.015) 4px)',
        }}
      />

      {/* 顶部系统标题 */}
      <div className="mb-10 text-center">
        <p className="font-display text-2xl font-black tracking-widest text-accent">
          TRAFFIC MONITOR
        </p>
        <p className="mt-1 text-xs tracking-[0.3em] text-text-secondary uppercase">
          Vehicle Detection &amp; Counting System
        </p>
      </div>

      {/* 登录卡片 */}
      <div
        className="relative w-full max-w-sm rounded-lg bg-bg-panel p-8"
        style={{
          border: '1px solid rgba(0,212,255,0.25)',
          boxShadow: '0 0 40px rgba(0,212,255,0.08), inset 0 1px 0 rgba(0,212,255,0.1)',
        }}
      >
        {/* 卡片顶部角标装饰 */}
        <span className="absolute left-0 top-0 h-4 w-4 border-l border-t border-accent" />
        <span className="absolute right-0 top-0 h-4 w-4 border-r border-t border-accent" />
        <span className="absolute bottom-0 left-0 h-4 w-4 border-b border-l border-accent" />
        <span className="absolute bottom-0 right-0 h-4 w-4 border-b border-r border-accent" />

        <h1 className="mb-6 font-display text-sm font-bold tracking-widest text-accent uppercase">
          系统登录
        </h1>

        <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
          {/* 用户名 */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="username"
              className="text-xs font-medium tracking-widest text-text-secondary uppercase"
            >
              用户名
            </label>
            <input
              ref={usernameRef}
              id="username"
              type="text"
              autoComplete="off"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              placeholder="输入用户名"
              className="
                w-full rounded-sm bg-bg-surface px-3 py-2.5 text-sm text-text-primary
                placeholder:text-text-secondary/40
                outline-none ring-1 ring-[#1E2D4A]
                transition-all duration-150
                focus:ring-accent/60
                disabled:opacity-50
              "
            />
          </div>

          {/* 密码 */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="password"
              className="text-xs font-medium tracking-widest text-text-secondary uppercase"
            >
              密码
            </label>
            <input
              id="password"
              type="password"
              autoComplete="off"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              placeholder="输入密码"
              className="
                w-full rounded-sm bg-bg-surface px-3 py-2.5 text-sm text-text-primary
                placeholder:text-text-secondary/40
                outline-none ring-1 ring-[#1E2D4A]
                transition-all duration-150
                focus:ring-accent/60
                disabled:opacity-50
              "
            />
          </div>

          {/* 错误提示 */}
          {error && (
            <div
              className="flex items-start gap-2 rounded-sm border border-alert-l4/30 bg-alert-l4/10 px-3 py-2.5 text-xs text-alert-l4"
              role="alert"
            >
              <span className="mt-0.5 shrink-0 text-[10px]">▲</span>
              <span>{error}</span>
            </div>
          )}

          {/* 提交按钮 */}
          <button
            type="submit"
            disabled={loading || !username.trim() || !password || lockMinutes !== null}
            className="
              relative mt-1 flex w-full items-center justify-center gap-2
              rounded-sm bg-accent/10 py-2.5 text-sm font-semibold
              tracking-widest text-accent uppercase
              ring-1 ring-accent/40
              transition-all duration-150
              hover:bg-accent/20 hover:ring-accent/70
              active:scale-[0.98]
              disabled:cursor-not-allowed disabled:opacity-40
            "
          >
            {loading && (
              <span className="h-3.5 w-3.5 animate-spin rounded-full border border-accent border-t-transparent" />
            )}
            {loading ? '验证中...' : '登 录'}
          </button>
        </form>
      </div>

      {/* 底部版本 */}
      <p className="mt-8 text-[10px] tracking-widest text-text-secondary/30 uppercase">
        v0.5.0 &nbsp;·&nbsp; CHELLJC
      </p>
    </div>
  )
}
