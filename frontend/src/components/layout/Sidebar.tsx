import { NavLink } from 'react-router-dom'
import {
  Activity,
  BarChart2,
  Settings,
  Users,
} from 'lucide-react'
import { useAuthStore } from '@/store/useAuthStore'

interface NavItem {
  to: string
  icon: React.ElementType
  label: string
  adminOnly?: boolean
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', icon: Activity, label: '实时监控' },
  { to: '/history', icon: BarChart2, label: '历史数据' },
  { to: '/settings', icon: Settings, label: '系统设置' },
  { to: '/users', icon: Users, label: '用户管理', adminOnly: true },
]

export function Sidebar() {
  const role = useAuthStore((s) => s.user?.role)

  return (
    <aside
      className="flex h-full w-16 flex-col items-center gap-1 border-r border-[#1E2D4A] bg-bg-panel py-4"
      style={{ boxShadow: 'inset -1px 0 0 rgba(0,212,255,0.05)' }}
    >
      {/* Logo mark */}
      <div className="mb-4 flex h-8 w-8 items-center justify-center rounded-sm bg-accent/10 ring-1 ring-accent/30">
        <span className="font-display text-xs font-black text-accent">T</span>
      </div>

      <nav className="flex flex-1 flex-col items-center gap-1">
        {NAV_ITEMS.filter((item) => !item.adminOnly || role === 'admin').map(
          ({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              title={label}
              className={({ isActive }) =>
                [
                  'group relative flex h-10 w-10 items-center justify-center rounded-sm transition-all duration-150',
                  isActive
                    ? 'bg-accent/15 text-accent ring-1 ring-accent/40'
                    : 'text-text-secondary hover:bg-bg-surface hover:text-text-primary',
                ].join(' ')
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={18} strokeWidth={isActive ? 2 : 1.5} />
                  {/* 激活指示线 */}
                  {isActive && (
                    <span className="absolute right-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-accent" />
                  )}
                  {/* Tooltip */}
                  <span className="pointer-events-none absolute left-full ml-2 whitespace-nowrap rounded-sm bg-bg-surface px-2 py-1 text-xs text-text-primary opacity-0 shadow-lg ring-1 ring-[#1E2D4A] transition-opacity group-hover:opacity-100">
                    {label}
                  </span>
                </>
              )}
            </NavLink>
          )
        )}
      </nav>
    </aside>
  )
}
