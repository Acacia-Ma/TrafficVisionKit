/**
 * 用户管理页面（设计稿 10.3 节，admin only）
 *
 * 功能：
 * - 用户列表 DataTable（username、角色、状态、最后登录、操作列）
 * - 新建用户对话框（含角色选择）
 * - 重置密码对话框
 * - 启用/禁用二次确认（ConfirmDialog）
 * - 删除用户二次确认（ConfirmDialog）
 */
import { createPortal } from 'react-dom'
import { useState } from 'react'
import { UserPlus, Users } from 'lucide-react'
import {
  useUsers,
  useCreateUser,
  useUpdateUser,
  useDeleteUser,
  useResetPassword,
} from '@/lib/api'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { DataTable } from '@/components/ui/DataTable'
import type { Column } from '@/components/ui/DataTable'
import { formatDateTime } from '@/lib/utils'
import type { UserInfo, UserCreate } from '@/types/api'

// ── 角色徽章 ──────────────────────────────────────────────────────────────────

function RoleBadge({ role }: { role: 'admin' | 'operator' }) {
  const isAdmin = role === 'admin'
  return (
    <span
      className="rounded-sm px-1.5 py-0.5 text-[9px] font-bold tracking-widest uppercase"
      style={{
        color: isAdmin ? '#00D4FF' : '#7A90B3',
        background: isAdmin ? 'rgba(0,212,255,0.1)' : 'rgba(122,144,179,0.1)',
        border: `1px solid ${isAdmin ? 'rgba(0,212,255,0.3)' : 'rgba(122,144,179,0.2)'}`,
      }}
    >
      {isAdmin ? 'Admin' : 'Operator'}
    </span>
  )
}

// ── 通用表单 Modal ─────────────────────────────────────────────────────────────

function FormModal({
  title,
  onClose,
  onSubmit,
  submitting,
  children,
}: {
  title: string
  onClose: () => void
  onSubmit: () => void
  submitting: boolean
  children: React.ReactNode
}) {
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-sm rounded-sm bg-bg-panel p-6 shadow-2xl ring-1 ring-[#1E2D4A]">
        <h2 className="mb-5 text-sm font-semibold tracking-widest text-text-primary uppercase">
          {title}
        </h2>
        <div className="flex flex-col gap-3">{children}</div>
        <div className="mt-5 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-sm px-4 py-2 text-xs text-text-secondary ring-1 ring-[#1E2D4A] transition hover:text-text-primary"
          >
            取消
          </button>
          <button
            onClick={onSubmit}
            disabled={submitting}
            className="flex items-center gap-1.5 rounded-sm bg-accent/10 px-5 py-2 text-xs font-medium text-accent ring-1 ring-accent/30 transition hover:bg-accent/20 disabled:opacity-40"
          >
            {submitting && (
              <span className="h-3 w-3 animate-spin rounded-full border border-accent border-t-transparent" />
            )}
            确认
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

function TextInput({
  label,
  type = 'text',
  value,
  onChange,
  placeholder,
  required,
}: {
  label: string
  type?: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  required?: boolean
}) {
  return (
    <div>
      <label className="mb-1 block text-[10px] text-text-secondary">
        {label}
        {required && <span className="ml-1 text-alert-l4">*</span>}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-sm bg-bg-surface px-2.5 py-1.5 text-xs text-text-primary ring-1 ring-[#1E2D4A] outline-none focus:ring-accent/50"
      />
    </div>
  )
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

type ConfirmType = 'toggle' | 'delete'

export default function UserManagement() {
  const [page, setPage] = useState(1)
  const [toast, setToast] = useState<{ ok: boolean; msg: string } | null>(null)

  // 对话框状态
  const [createOpen, setCreateOpen] = useState(false)
  const [confirmState, setConfirmState] = useState<{ type: ConfirmType; user: UserInfo } | null>(null)
  const [resetUser, setResetUser] = useState<UserInfo | null>(null)

  // 新建用户表单
  const [newUser, setNewUser] = useState<UserCreate>({
    username: '',
    password: '',
    full_name: '',
    email: '',
    role: 'operator',
  })
  const [createConfirmPw, setCreateConfirmPw] = useState('')
  const [createError, setCreateError] = useState('')

  // 重置密码表单
  const [resetPw, setResetPw] = useState('')
  const [resetPwConfirm, setResetPwConfirm] = useState('')
  const [resetError, setResetError] = useState('')

  // API 钩子
  const { data: usersData, isLoading } = useUsers({ page, page_size: 20 })
  const { mutate: createUser, isPending: creating } = useCreateUser()
  const { mutate: updateUser, isPending: toggling } = useUpdateUser(
    confirmState?.type === 'toggle' ? (confirmState.user.id) : 0,
  )
  const { mutate: deleteUser, isPending: deleting } = useDeleteUser()
  const { mutate: resetPassword, isPending: resetting } = useResetPassword(
    resetUser?.id ?? 0,
  )

  const showToast = (ok: boolean, msg: string) => {
    setToast({ ok, msg })
    setTimeout(() => setToast(null), 3000)
  }

  // ── 新建用户 ──
  const handleCreate = () => {
    if (!newUser.username || !newUser.password || !newUser.full_name) {
      setCreateError('请填写必填项（用户名、密码、姓名）')
      return
    }
    if (newUser.password !== createConfirmPw) {
      setCreateError('两次输入密码不一致')
      return
    }
    setCreateError('')
    createUser(
      { ...newUser, email: newUser.email || undefined },
      {
        onSuccess: () => {
          showToast(true, `✓ 用户 ${newUser.username} 创建成功`)
          setCreateOpen(false)
          setNewUser({ username: '', password: '', full_name: '', email: '', role: 'operator' })
          setCreateConfirmPw('')
        },
        onError: (err: unknown) => {
          const msg = (err as { response?: { data?: { detail?: { message?: string } } } })
            ?.response?.data?.detail?.message
          setCreateError(msg ?? '创建失败，用户名可能已存在')
        },
      },
    )
  }

  // ── 启用 / 禁用 ──
  const handleToggle = () => {
    if (!confirmState || confirmState.type !== 'toggle') return
    const { user } = confirmState
    updateUser(
      { is_active: !user.is_active },
      {
        onSuccess: () => {
          showToast(true, `✓ ${user.username} 已${user.is_active ? '禁用' : '启用'}`)
          setConfirmState(null)
        },
        onError: () => {
          showToast(false, '✗ 操作失败，请重试')
          setConfirmState(null)
        },
      },
    )
  }

  // ── 删除 ──
  const handleDelete = () => {
    if (!confirmState || confirmState.type !== 'delete') return
    const { user } = confirmState
    deleteUser(user.id, {
      onSuccess: () => {
        showToast(true, `✓ 用户 ${user.username} 已删除`)
        setConfirmState(null)
      },
      onError: () => {
        showToast(false, '✗ 删除失败，请重试')
        setConfirmState(null)
      },
    })
  }

  // ── 重置密码 ──
  const handleResetPassword = () => {
    if (!resetPw) { setResetError('请输入新密码'); return }
    if (resetPw !== resetPwConfirm) { setResetError('两次密码不一致'); return }
    setResetError('')
    resetPassword(resetPw, {
      onSuccess: () => {
        showToast(true, `✓ ${resetUser?.username} 密码已重置`)
        setResetUser(null)
        setResetPw('')
        setResetPwConfirm('')
      },
      onError: (err: unknown) => {
        const msg = (err as { response?: { data?: { detail?: { message?: string } } } })
          ?.response?.data?.detail?.message
        setResetError(msg ?? '重置失败，密码强度可能不足')
      },
    })
  }

  // ── 表格列定义 ──
  const columns: Column<UserInfo>[] = [
    {
      key: 'username',
      header: '用户名',
      render: (row) => (
        <span className="font-mono text-xs text-text-primary">{row.username}</span>
      ),
    },
    {
      key: 'full_name',
      header: '姓名',
      render: (row) => <span className="text-xs">{row.full_name}</span>,
    },
    {
      key: 'role',
      header: '角色',
      render: (row) => <RoleBadge role={row.role} />,
      className: 'w-24',
    },
    {
      key: 'is_active',
      header: '状态',
      render: (row) =>
        row.is_active ? (
          <span className="text-xs text-online">启用</span>
        ) : (
          <span className="text-xs text-text-secondary/50">禁用</span>
        ),
      className: 'w-16',
    },
    {
      key: 'last_login_at',
      header: '最后登录',
      render: (row) => (
        <span className="text-xs text-text-secondary">
          {row.last_login_at ? formatDateTime(row.last_login_at) : '—'}
        </span>
      ),
      className: 'w-40',
    },
    {
      key: 'id',
      header: '操作',
      render: (row) => (
        <div className="flex items-center gap-2">
          {/* 启用/禁用 */}
          <button
            onClick={() => setConfirmState({ type: 'toggle', user: row })}
            className="text-[10px] text-text-secondary transition hover:text-text-primary"
          >
            {row.is_active ? '禁用' : '启用'}
          </button>
          <span className="text-[#1E2D4A]">|</span>
          {/* 重置密码 */}
          <button
            onClick={() => {
              setResetUser(row)
              setResetPw('')
              setResetPwConfirm('')
              setResetError('')
            }}
            className="text-[10px] text-text-secondary transition hover:text-accent"
          >
            重置密码
          </button>
          <span className="text-[#1E2D4A]">|</span>
          {/* 删除 */}
          <button
            onClick={() => setConfirmState({ type: 'delete', user: row })}
            className="text-[10px] text-text-secondary transition hover:text-alert-l4"
          >
            删除
          </button>
        </div>
      ),
      className: 'w-44',
    },
  ]

  return (
    <div className="h-full overflow-auto p-6">
      <div className="mx-auto max-w-5xl">

        {/* 标题 */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Users size={18} className="text-accent" />
            <h1 className="text-sm font-semibold tracking-widest text-text-primary uppercase">
              用户管理
            </h1>
            {usersData && (
              <span className="font-mono text-[10px] text-text-secondary/50">
                共 {usersData.total} 位用户
              </span>
            )}
          </div>

          <button
            onClick={() => {
              setCreateOpen(true)
              setCreateError('')
            }}
            className="flex items-center gap-1.5 rounded-sm bg-accent/10 px-3 py-2 text-xs font-medium text-accent ring-1 ring-accent/30 transition hover:bg-accent/20"
          >
            <UserPlus size={12} />
            新建用户
          </button>
        </div>

        {/* 用户表格 */}
        <DataTable<UserInfo>
          columns={columns}
          data={usersData?.items ?? []}
          total={usersData?.total ?? 0}
          page={page}
          pageSize={20}
          onPageChange={setPage}
          rowKey={(r) => r.id}
          loading={isLoading}
        />
      </div>

      {/* ── 新建用户 Modal ── */}
      {createOpen && (
        <FormModal
          title="新建用户"
          onClose={() => setCreateOpen(false)}
          onSubmit={handleCreate}
          submitting={creating}
        >
          <TextInput
            label="用户名"
            value={newUser.username}
            onChange={(v) => setNewUser((f) => ({ ...f, username: v }))}
            placeholder="仅限字母数字下划线"
            required
          />
          <TextInput
            label="姓名"
            value={newUser.full_name}
            onChange={(v) => setNewUser((f) => ({ ...f, full_name: v }))}
            required
          />
          <TextInput
            label="密码"
            type="password"
            value={newUser.password}
            onChange={(v) => setNewUser((f) => ({ ...f, password: v }))}
            placeholder="至少 8 位，含大小写和数字"
            required
          />
          <TextInput
            label="确认密码"
            type="password"
            value={createConfirmPw}
            onChange={setCreateConfirmPw}
            required
          />
          <div>
            <label className="mb-1 block text-[10px] text-text-secondary">
              角色 <span className="text-alert-l4">*</span>
            </label>
            <select
              value={newUser.role}
              onChange={(e) =>
                setNewUser((f) => ({
                  ...f,
                  role: e.target.value as 'admin' | 'operator',
                }))
              }
              className="w-full rounded-sm bg-bg-surface px-2.5 py-1.5 text-xs text-text-primary ring-1 ring-[#1E2D4A] outline-none focus:ring-accent/50"
            >
              <option value="operator">Operator（普通）</option>
              <option value="admin">Admin（管理员）</option>
            </select>
          </div>
          <TextInput
            label="邮箱（可选）"
            type="email"
            value={newUser.email ?? ''}
            onChange={(v) => setNewUser((f) => ({ ...f, email: v }))}
          />
          {createError && (
            <p className="rounded-sm bg-alert-l4/10 px-2.5 py-1.5 text-[10px] text-alert-l4 ring-1 ring-alert-l4/30">
              {createError}
            </p>
          )}
        </FormModal>
      )}

      {/* ── 重置密码 Modal ── */}
      {resetUser && (
        <FormModal
          title={`重置密码 — ${resetUser.username}`}
          onClose={() => setResetUser(null)}
          onSubmit={handleResetPassword}
          submitting={resetting}
        >
          <TextInput
            label="新密码"
            type="password"
            value={resetPw}
            onChange={setResetPw}
            placeholder="至少 8 位，含大小写和数字"
            required
          />
          <TextInput
            label="确认新密码"
            type="password"
            value={resetPwConfirm}
            onChange={setResetPwConfirm}
            required
          />
          {resetError && (
            <p className="rounded-sm bg-alert-l4/10 px-2.5 py-1.5 text-[10px] text-alert-l4 ring-1 ring-alert-l4/30">
              {resetError}
            </p>
          )}
        </FormModal>
      )}

      {/* ── 启用/禁用 ConfirmDialog ── */}
      <ConfirmDialog
        isOpen={confirmState?.type === 'toggle'}
        title={
          confirmState?.user.is_active
            ? `禁用用户 ${confirmState?.user.username}`
            : `启用用户 ${confirmState?.user.username}`
        }
        message={
          confirmState?.user.is_active
            ? '禁用后该用户将无法登录，确认操作？'
            : '启用后该用户可正常登录，确认操作？'
        }
        onConfirm={handleToggle}
        onCancel={() => setConfirmState(null)}
        loading={toggling}
      />

      {/* ── 删除 ConfirmDialog ── */}
      <ConfirmDialog
        isOpen={confirmState?.type === 'delete'}
        title={`删除用户 ${confirmState?.user.username}`}
        message="此操作不可撤销，确认删除？"
        onConfirm={handleDelete}
        onCancel={() => setConfirmState(null)}
        loading={deleting}
      />

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
