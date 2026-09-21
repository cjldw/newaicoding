/**
 * 设置页布局 — 左侧导航 + 右侧内容区
 */

import { NavLink, Outlet } from 'react-router-dom'
import { User, Key } from 'lucide-react'

const navItems = [
  { to: '/settings/profile', label: '个人资料', icon: User },
  { to: '/settings/gitlab-token', label: 'GitLab Token', icon: Key },
]

export function SettingsLayout() {
  return (
    <div className="min-h-screen bg-bg py-8 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-2xl font-semibold text-text mb-6">设置</h1>
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
    </div>
  )
}
