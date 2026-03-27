/** 业务实体类型（供 UI 组件使用，与 API 类型平行） */

import type { AlertEventPayload } from './websocket'

// 预警列表项（来自 alert_event WS 消息，用于前端实时列表）
export type AlertItem = AlertEventPayload & {
  device_id: number
}

// 实时折线图数据点
export interface TimeSeriesPoint {
  time: string
  value: number
}

// 设备在线状态
export type DeviceStatus = 'online' | 'offline' | 'warning'

// 预警等级 0~5
export type AlertLevel = 0 | 1 | 2 | 3 | 4 | 5

// 用户角色
export type UserRole = 'admin' | 'operator'
