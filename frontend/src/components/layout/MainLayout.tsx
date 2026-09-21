/**
 * MainLayout — 主布局: 左侧导航 + 右侧内容区
 * - 导航项: 工作台 / 项目 / 平台设置(superadmin 可见)
 */

import { NavLink, Outlet } from 'react-router-dom'
import { LayoutDashboard, FolderKanban, Settings, Sparkles } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'

const navItems = [
  { to: '/', label: '工作台', icon: LayoutDashboard, end: true },
  { to: '/projects', label: '项目', icon: FolderKanban, end: false },
]

export function MainLayout() {
  const user = useAuthStore((s) => s.user)
  const isSuperadmin = user?.role === 'superadmin'

  return (
    <div className="flex min-h-screen bg-bg">
      {/* 左侧导航 */}
      <aside className="w-56 border-r border-border bg-surface flex flex-col">
        <div className="px-4 py-5 border-b border-border">
          <h1 className="text-lg font-semibold text-text">AI 开发平台</h1>
        </div>
        <nav className="flex-1 px-2 py-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                  isActive
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'text-text-muted hover:bg-surface-strong hover:text-text'
                }`
              }
            >
              <item.icon className="w-4 h-4" />
              {item.label}
            </NavLink>
          ))}
          {isSuperadmin && (
            <>
              <NavLink
                to="/admin/skills"
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                    isActive
                      ? 'bg-primary/10 text-primary font-medium'
                      : 'text-text-muted hover:bg-surface-strong hover:text-text'
                  }`
                }
              >
                <Sparkles className="w-4 h-4" />
                Skills 市场
              </NavLink>
              <NavLink
                to="/admin/platform-settings"
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                    isActive
                      ? 'bg-primary/10 text-primary font-medium'
                      : 'text-text-muted hover:bg-surface-strong hover:text-text'
                  }`
                }
              >
                <Settings className="w-4 h-4" />
                平台设置
              </NavLink>
            </>
          )}
        </nav>
      </aside>

      {/* 右侧内容 */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
