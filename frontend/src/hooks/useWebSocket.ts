/**
 * 底层 WebSocket Hook：连接管理 + 指数退避重连。
 *
 * 设计原则（见设计稿 15.4 节规范三）：
 *   - 只负责连接管理，不解析业务消息
 *   - 上层 useStreamSocket / useHealthSocket 负责消息解析
 *
 * 重连策略：1s → 2s → 4s → 8s → 16s → 30s（封顶），无限重试
 * 特殊处理：close code 4401 → 不走重连，触发 onClose(4401)，由调用方刷新 Token
 */
import { useCallback, useEffect, useRef, useState } from 'react'

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16_000, 30_000]

interface Options {
  /** WebSocket URL，null / undefined 时不连接 */
  url: string | null | undefined
  onMessage: (data: unknown) => void
  onOpen?: () => void
  /** code=4401 时由调用方处理 Token 刷新，不自动重连 */
  onClose?: (code: number) => void
  /** false 时主动断开并不重连 */
  enabled?: boolean
}

interface Return {
  isConnected: boolean
  /** 发送文本消息 */
  send: (data: string) => void
  /** 主动断开（不触发重连） */
  disconnect: () => void
}

export function useWebSocket({
  url,
  onMessage,
  onOpen,
  onClose,
  enabled = true,
}: Options): Return {
  const [isConnected, setIsConnected] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const attemptRef = useRef(0)
  const intentionalRef = useRef(false)   // 主动断开标志
  const mountedRef = useRef(true)

  // 用 ref 保存回调，避免 effect 依赖变化引起不必要的重连
  const onMessageRef = useRef(onMessage)
  const onOpenRef = useRef(onOpen)
  const onCloseRef = useRef(onClose)
  useEffect(() => { onMessageRef.current = onMessage }, [onMessage])
  useEffect(() => { onOpenRef.current = onOpen }, [onOpen])
  useEffect(() => { onCloseRef.current = onClose }, [onClose])

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const connect = useCallback(() => {
    // mountedRef 在 StrictMode 双挂载时可能为 false，需重置
    mountedRef.current = true
    if (!url || !enabled) return

    // 关闭旧连接（不触发 onclose 处理器）
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.close()
      wsRef.current = null
    }

    intentionalRef.current = false
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return }
      attemptRef.current = 0
      setIsConnected(true)
      onOpenRef.current?.()
    }

    ws.onmessage = (event: MessageEvent) => {
      if (!mountedRef.current) return
      try {
        onMessageRef.current(JSON.parse(event.data as string))
      } catch {
        onMessageRef.current(event.data)
      }
    }

    ws.onclose = (event: CloseEvent) => {
      if (!mountedRef.current) return
      setIsConnected(false)
      onCloseRef.current?.(event.code)

      // 主动断开 或 Token 过期（4401） → 不重连
      if (intentionalRef.current || event.code === 4401) return

      // 指数退避重连
      const delay =
        RECONNECT_DELAYS[Math.min(attemptRef.current, RECONNECT_DELAYS.length - 1)]
      attemptRef.current++
      timerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      // onerror 后 onclose 会紧接触发，在那里处理重连
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, enabled])

  // url 或 enabled 变化时重新建立连接
  useEffect(() => {
    clearTimer()
    if (url && enabled) {
      connect()
    } else {
      intentionalRef.current = true
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
        wsRef.current = null
      }
      setIsConnected(false)
    }

    return () => {
      clearTimer()
      intentionalRef.current = true
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
        wsRef.current = null
      }
    }
  // connect 是 memoized by useCallback，url/enabled 变化时重新生成
  }, [connect, url, enabled, clearTimer])

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      mountedRef.current = false
    }
  }, [])

  const disconnect = useCallback(() => {
    clearTimer()
    intentionalRef.current = true
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.close()
      wsRef.current = null
    }
    setIsConnected(false)
  }, [clearTimer])

  const send = useCallback((data: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data)
    }
  }, [])

  return { isConnected, send, disconnect }
}
