/**
 * 设置页布局 — 嵌套于 MainLayout 的二级布局
 * - 路由层级:MainLayout(全局侧栏/顶栏/面包屑) > SettingsLayout(本组件) > 具体设置页
 * - 容器走平台 .page 体系(表单区,不加 .wide,保持限宽);不再自带独立壳
 *   (原 min-h-screen/py-8/max-w-4xl 居中 + 壳级 h1「设置」已移除,避免与页内 h1 双层标题)
 * - 结构:.page 容器内 flex —— 左导航(w-48,激活态保留)+ 右内容 Outlet
 */

import { NavLink, Outlet } from 'react-router-dom'
import { User, Key, Bell } from 'lucide-react'

const navItems = [
  { to: '/settings/profile', label: '个人资料', icon: User },
  { to: '/settings/gitlab-token', label: 'GitLab Token', icon: Key },
  { to: '/settings/notifications', label: '通知设置', icon: Bell },
]

export function SettingsLayout() {
  return (
    <div className="page">
      <div className="flex gap-8">
        {/* 左侧导航 */}
        <nav className="w-48 flex-shrink-0">
          <ul className="space-y-1">
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end
                  className={({ isActive }) =>
                    `flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
                      isActive
                        ? 'bg-surface-strong text-text font-medium'
                        : 'text-text-muted hover:text-text hover:bg-surface'
                    }`
                  }
                >
                  <item.icon className="w-4 h-4" />
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        {/* 右侧内容区 */}
        <div className="flex-1 min-w-0">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
