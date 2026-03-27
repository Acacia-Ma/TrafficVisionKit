/**
 * 健康状态 WebSocket Hook：订阅 /ws/health。
 *
 * 功能：
 *   - 接收 health_report 消息，通过回调传递给调用方
 *   - 每 30s 发送心跳 ping，保活连接
 *   - close code 4401 处理方式与 useStreamSocket 一致
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useWebSocket } from './useWebSocket'
import { useAuthStore } from '@/store/useAuthStore'
import { authApi } from '@/lib/api'
import type { HealthReportMsg } from '@/types/websocket'

const WS_BASE = import.meta.env['VITE_WS_BASE_URL'] ?? 'ws://localhost:8000'
const PING_INTERVAL_MS = 30_000

interface UseHealthSocketOptions {
  onReport: (report: HealthReportMsg) => void
  enabled?: boolean
}

interface UseHealthSocketReturn {
  isConnected: boolean
}

export function useHealthSocket({
  onReport,
  enabled = true,
}: UseHealthSocketOptions): UseHealthSocketReturn {
  const navigate = useNavigate()
  const { setTokens, clearAuth } = useAuthStore()
  const [activeToken, setActiveToken] = useState(
    () => useAuthStore.getState().accessToken
  )
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const sendRef = useRef<((data: string) => void) | null>(null)

  useEffect(() => {
    return useAuthStore.subscribe((s) => {
      if (s.accessToken && s.accessToken !== activeToken) {
        setActiveToken(s.accessToken)
      }
    })
  }, [activeToken])

  const wsUrl =
    activeToken && enabled
      ? `${WS_BASE}/ws/health?token=${activeToken}`
      : null

  const handleMessage = useCallback(
    (raw: unknown) => {
      const msg = raw as { type: string }
      if (msg.type === 'health_report') {
        onReport(msg as HealthReportMsg)
      }
    },
    [onReport]
  )

  const handleOpen = useCallback(() => {
    // 建立定时 ping
    pingTimerRef.current = setInterval(() => {
      sendRef.current?.(
        JSON.stringify({ type: 'ping', timestamp: new Date().toISOString() })
      )
    }, PING_INTERVAL_MS)
  }, [])

  const handleClose = useCallback(
    async (code: number) => {
      if (pingTimerRef.current) {
        clearInterval(pingTimerRef.current)
        pingTimerRef.current = null
      }

      if (code !== 4401) return

      try {
        const data = await authApi.refresh()
        setTokens(data.access_token, data.user)
        setActiveToken(data.access_token)
      } catch {
        clearAuth()
        navigate('/login', { replace: true })
      }
    },
    [setTokens, clearAuth, navigate]
  )

  const { isConnected, send } = useWebSocket({
    url: wsUrl,
    onMessage: handleMessage,
    onOpen: handleOpen,
    onClose: handleClose,
    enabled: enabled && !!activeToken,
  })

  // 将 send 存入 ref 供 ping interval 使用
  useEffect(() => {
    sendRef.current = send
  }, [send])

  // 卸载时清除 ping 定时器
  useEffect(() => {
    return () => {
      if (pingTimerRef.current) {
        clearInterval(pingTimerRef.current)
        pingTimerRef.current = null
      }
    }
  }, [])

  return { isConnected }
}
