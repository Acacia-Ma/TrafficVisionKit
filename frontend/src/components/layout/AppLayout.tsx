import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { Footer } from './Footer'

/**
 * 整体布局：侧边栏（固定宽度）+ 右侧主区（Header / 内容 / Footer 垂直堆叠）
 *
 * ┌────┬───────────────────────────┐
 * │    │  Header (h-12)            │
 * │ S  ├───────────────────────────┤
 * │ i  │                           │
 * │ d  │  <Outlet />  (flex-1)     │
 * │ e  │                           │
 * │ b  ├───────────────────────────┤
 * │    │  Footer (h-7)             │
 * └────┴───────────────────────────┘
 */
export function AppLayout() {
  return (
    <div className="flex h-full bg-bg-base">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
        <Footer />
      </div>
    </div>
  )
}
