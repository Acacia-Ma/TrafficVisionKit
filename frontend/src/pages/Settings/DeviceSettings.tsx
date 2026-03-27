/**
 * 设备参数配置页面（设计稿 10.1 节）
 *
 * 表单字段：line_y（带实时预览）、confidence、fps_limit、
 *           alert_l2/l3/l4 阈值、park_timeout_seconds
 * 保存后调 PUT /api/devices/{id}/settings，成功 Toast 提示「配置已生效」
 */
import { useEffect, useState } from 'react'
import { Settings } from 'lucide-react'
import { useDevices, useDeviceSettings, useUpdateDeviceSettings } from '@/lib/api'
import { useTrafficStore } from '@/store/useTrafficStore'
import type { DeviceSettingsUpdate } from '@/types/api'

// ── 子组件 ────────────────────────────────────────────────────────────────────

function FieldRow({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-4 border-b border-[#1E2D4A]/60 py-2.5 last:border-0">
      <div className="w-36 shrink-0">
        <p className="text-xs text-text-primary">{label}</p>
        {hint && <p className="mt-0.5 text-[10px] text-text-secondary/50">{hint}</p>}
      </div>
      <div className="flex-1">{children}</div>
    </div>
  )
}

function NumInput({
  value,
  min,
  max,
  step = 1,
  onChange,
}: {
  value: number
  min?: number
  max?: number
  step?: number
  onChange: (v: number) => void
}) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={(e) => {
        const v = Number(e.target.value)
        if (!isNaN(v)) onChange(v)
      }}
      className="w-24 rounded-sm bg-bg-surface px-2.5 py-1 font-mono text-xs text-text-primary ring-1 ring-[#1E2D4A] outline-none focus:ring-accent/60"
    />
  )
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

type FormState = Required<DeviceSettingsUpdate>

const DEFAULT_FORM: FormState = {
  line_y: 240,
  confidence: 0.5,
  fps_limit: 30,
  alert_l2_threshold: 5,
  alert_l3_threshold: 10,
  alert_l4_threshold: 15,
  park_timeout_seconds: 30,
}

export default function DeviceSettings() {
  const globalDeviceId = useTrafficStore((s) => s.selectedDeviceId)
  const [deviceId, setDeviceId] = useState(globalDeviceId)
  const [form, setForm] = useState<FormState>(DEFAULT_FORM)
  const [toast, setToast] = useState<{ ok: boolean; msg: string } | null>(null)

  const { data: devices } = useDevices()
  const { data: settings, isLoading } = useDeviceSettings(deviceId)
  const { mutate: save, isPending: saving } = useUpdateDeviceSettings(deviceId)

  // 加载/切换设备时同步表单
  useEffect(() => {
    if (settings) {
      setForm({
        line_y: settings.line_y,
        confidence: settings.confidence,
        fps_limit: settings.fps_limit,
        alert_l2_threshold: settings.alert_l2_threshold,
        alert_l3_threshold: settings.alert_l3_threshold,
        alert_l4_threshold: settings.alert_l4_threshold,
        park_timeout_seconds: settings.park_timeout_seconds,
      })
    }
  }, [settings])

  const showToast = (ok: boolean, msg: string) => {
    setToast({ ok, msg })
    setTimeout(() => setToast(null), 3000)
  }

  const handleSave = () => {
    save(form, {
      onSuccess: () => showToast(true, '✓ 配置已生效，推理协程将在下一帧重载'),
      onError: () => showToast(false, '✗ 保存失败，请检查参数范围'),
    })
  }

  const handleReset = () => {
    if (settings) {
      setForm({
        line_y: settings.line_y,
        confidence: settings.confidence,
        fps_limit: settings.fps_limit,
        alert_l2_threshold: settings.alert_l2_threshold,
        alert_l3_threshold: settings.alert_l3_threshold,
        alert_l4_threshold: settings.alert_l4_threshold,
        park_timeout_seconds: settings.park_timeout_seconds,
      })
    }
  }

  const pf = (v: number) => v.toFixed(2)
  const resH = settings?.resolution_h ?? 480
  const resW = settings?.resolution_w ?? 640
  const lineTopPct = Math.min(100, (form.line_y / resH) * 100)

  return (
    <div className="h-full overflow-auto p-6">
      <div className="mx-auto max-w-3xl">

        {/* 标题 */}
        <div className="mb-6 flex items-center gap-3">
          <Settings size={18} className="text-accent" />
          <h1 className="text-sm font-semibold tracking-widest text-text-primary uppercase">
            设备参数配置
          </h1>
        </div>

        {/* 设备选择 */}
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <span className="text-xs text-text-secondary">设备：</span>
          <select
            value={deviceId}
            onChange={(e) => setDeviceId(Number(e.target.value))}
            className="rounded-sm bg-bg-surface px-2.5 py-1.5 text-xs text-text-primary ring-1 ring-[#1E2D4A] outline-none focus:ring-accent/50"
          >
            {devices?.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
          {settings && (
            <span className="font-mono text-[10px] text-text-secondary/40">
              最后更新：{new Date(settings.updated_at).toLocaleString('zh-CN')}
            </span>
          )}
        </div>

        {isLoading ? (
          <div className="flex h-48 items-center justify-center">
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_260px]">

            {/* 左列：表单 */}
            <div className="rounded-sm bg-bg-panel p-4 ring-1 ring-[#1E2D4A]">

              {/* 基础参数 */}
              <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-accent/70">
                基础参数
              </p>

              <FieldRow label="计数线 Y 坐标" hint={`像素，0 ~ ${resH}`}>
                <div className="flex items-center gap-3">
                  <NumInput
                    value={form.line_y}
                    min={0}
                    max={resH}
                    onChange={(v) => setForm((f) => ({ ...f, line_y: Math.min(resH, Math.max(0, v)) }))}
                  />
                  <input
                    type="range"
                    min={0}
                    max={resH}
                    value={form.line_y}
                    onChange={(e) => setForm((f) => ({ ...f, line_y: Number(e.target.value) }))}
                    className="w-28 accent-cyan-400"
                  />
                </div>
              </FieldRow>

              <FieldRow label="YOLO 置信度" hint="0.1 ~ 0.9">
                <div className="flex items-center gap-3">
                  <span className="w-8 font-mono text-xs text-accent">{pf(form.confidence)}</span>
                  <input
                    type="range"
                    min={0.1}
                    max={0.9}
                    step={0.05}
                    value={form.confidence}
                    onChange={(e) => setForm((f) => ({ ...f, confidence: Number(e.target.value) }))}
                    className="w-32 accent-cyan-400"
                  />
                </div>
              </FieldRow>

              <FieldRow label="帧率上限" hint="fps，1 ~ 60">
                <NumInput
                  value={form.fps_limit}
                  min={1}
                  max={60}
                  onChange={(v) => setForm((f) => ({ ...f, fps_limit: v }))}
                />
              </FieldRow>

              {/* 预警阈值 */}
              <p className="mb-3 mt-5 text-[10px] font-semibold uppercase tracking-widest text-accent/70">
                拥堵预警阈值（辆）
              </p>

              <FieldRow label="L2 黄色">
                <NumInput
                  value={form.alert_l2_threshold}
                  min={1}
                  onChange={(v) => setForm((f) => ({ ...f, alert_l2_threshold: v }))}
                />
              </FieldRow>

              <FieldRow label="L3 橙色">
                <NumInput
                  value={form.alert_l3_threshold}
                  min={1}
                  onChange={(v) => setForm((f) => ({ ...f, alert_l3_threshold: v }))}
                />
              </FieldRow>

              <FieldRow label="L4 红色">
                <NumInput
                  value={form.alert_l4_threshold}
                  min={1}
                  onChange={(v) => setForm((f) => ({ ...f, alert_l4_threshold: v }))}
                />
              </FieldRow>

              {/* 异常停车 */}
              <p className="mb-3 mt-5 text-[10px] font-semibold uppercase tracking-widest text-accent/70">
                异常停车检测
              </p>

              <FieldRow label="静止判定秒数" hint="park_timeout，5 ~ 300">
                <NumInput
                  value={form.park_timeout_seconds}
                  min={5}
                  max={300}
                  onChange={(v) => setForm((f) => ({ ...f, park_timeout_seconds: v }))}
                />
              </FieldRow>
            </div>

            {/* 右列：预览 + 说明 */}
            <div className="flex flex-col gap-4">

              {/* 虚拟线预览 */}
              <div className="rounded-sm bg-bg-panel p-4 ring-1 ring-[#1E2D4A]">
                <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-accent/70">
                  计数线预览
                </p>
                <div
                  className="relative w-full overflow-hidden rounded-sm bg-[#060B18]"
                  style={{ aspectRatio: '4/3' }}
                >
                  {/* 扫描线 */}
                  <div
                    className="pointer-events-none absolute inset-0"
                    style={{
                      background:
                        'repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(0,0,0,0.08) 3px, rgba(0,0,0,0.08) 4px)',
                    }}
                  />
                  {/* 计数线 */}
                  <div
                    className="pointer-events-none absolute inset-x-0 transition-all duration-100"
                    style={{ top: `${lineTopPct}%` }}
                  >
                    <div className="h-px w-full bg-accent/80" />
                    <div className="flex justify-between px-1">
                      <span className="font-mono text-[7px] text-accent/60">COUNT LINE</span>
                      <span className="font-mono text-[7px] text-accent/60">Y={form.line_y}</span>
                    </div>
                  </div>
                  <span className="absolute bottom-1 right-1 font-mono text-[7px] text-text-secondary/25">
                    {resW}×{resH}
                  </span>
                </div>
              </div>

              {/* 阈值说明卡片 */}
              <div className="rounded-sm bg-bg-panel p-4 ring-1 ring-[#1E2D4A]">
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-accent/70">
                  预警等级
                </p>
                {[
                  { label: 'L2', color: '#FFC107', val: form.alert_l2_threshold, desc: '黄色拥堵' },
                  { label: 'L3', color: '#FF7043', val: form.alert_l3_threshold, desc: '橙色拥堵' },
                  { label: 'L4', color: '#F44336', val: form.alert_l4_threshold, desc: '红色拥堵' },
                ].map(({ label, color, val, desc }) => (
                  <div key={label} className="flex items-center gap-2 py-1">
                    <span
                      className="rounded-sm px-1.5 py-0.5 text-[9px] font-bold tracking-widest"
                      style={{ color, background: `${color}22`, border: `1px solid ${color}44` }}
                    >
                      {label}
                    </span>
                    <span className="text-[10px] text-text-secondary">
                      ≥ {val} 辆 · {desc}
                    </span>
                  </div>
                ))}
                <div className="mt-2 border-t border-[#1E2D4A]/60 pt-2">
                  <span className="text-[10px] text-text-secondary">
                    静止 {form.park_timeout_seconds}s → 异常停车 L3
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 底部按钮 */}
        {!isLoading && (
          <div className="mt-6 flex justify-end gap-3">
            <button
              onClick={handleReset}
              className="rounded-sm px-4 py-2 text-xs text-text-secondary ring-1 ring-[#1E2D4A] transition hover:text-text-primary"
            >
              重置
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 rounded-sm bg-accent/10 px-5 py-2 text-xs font-medium text-accent ring-1 ring-accent/30 transition hover:bg-accent/20 disabled:opacity-40"
            >
              {saving && (
                <span className="h-3 w-3 animate-spin rounded-full border border-accent border-t-transparent" />
              )}
              保存配置
            </button>
          </div>
        )}
      </div>

      {/* Toast 通知 */}
      {toast && (
        <div
          className={[
            'fixed bottom-6 right-6 z-50 rounded-sm px-4 py-2.5 text-xs font-medium shadow-xl ring-1',
            toast.ok
              ? 'bg-bg-panel text-online ring-online/40'
              : 'bg-bg-panel text-alert-l4 ring-alert-l4/40',
          ].join(' ')}
        >
          {toast.msg}
        </div>
      )}
    </div>
  )
}
