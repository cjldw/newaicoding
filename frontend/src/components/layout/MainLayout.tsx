/**
 * MainLayout — 主布局(R19/R20 对齐 vp 原型外壳)
 * - .shell: 220px 侧边栏(.sidebar:.logo/.sgroup/.sitem/.cnt/.tour)+ .main(.topbar + Outlet)
 * - 侧边栏分组: 顶部(工作台)/ 项目管理(列表+四维)/ 知识(知识条目+知识库)/ 平台管理·仅超管
 * - 顶栏: 面包屑占位 + 站内信铃铛 + 用户头像/退出
 */

import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, FolderKanban, ListChecks, Activity, FlaskConical, Rocket,
  BookOpen, Server, Users, ScrollText, Settings, Bell, LogOut,
} from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'

const LOGO_MARK = (
  <svg width="17" height="17" viewBox="0 0 32 32" aria-hidden>
    <rect width="32" height="32" rx="7" fill="#18181b" />
    <rect x="7.2" y="6" width="2.6" height="21" rx="1.3" fill="#ffffff" />
    <path d="M10.4 7.6 24 13.2 10.4 13.2Z" fill="#3b82f6" />
    <path d="M10.4 13.2H24l-7 2.9h-6.6Z" fill="#d4d4d8" />
    <path d="M10.4 16.1h6.6L10.4 19Z" fill="#a1a1aa" />
  </svg>
)

interface NavItem {
  to: string
  label: string
  icon: typeof LayoutDashboard
  end?: boolean
  count?: string
}

const NAV_TOP: NavItem[] = [
  { to: '/', label: '工作台', icon: LayoutDashboard, end: true },
]

const NAV_PROJECT: NavItem[] = [
  { to: '/projects', label: '项目列表', icon: FolderKanban },
  { to: '/manage/requirements', label: '需求管理', icon: ListChecks },
  { to: '/manage/tasks', label: '任务管理', icon: Activity },
  { to: '/manage/tests', label: '测试管理', icon: FlaskConical },
  { to: '/manage/releases', label: '发布管理', icon: Rocket },
]

const NAV_KB: NavItem[] = [
  { to: '/knowledge', label: '知识条目', icon: BookOpen },
]

const NAV_ADMIN: NavItem[] = [
  { to: '/admin/runners', label: 'Runner 管理', icon: Server },
  { to: '/admin/users', label: '用户管理', icon: Users },
  { to: '/admin/audit-logs', label: '审计日志', icon: ScrollText },
  { to: '/admin/platform-settings', label: '平台设置', icon: Settings },
]

function SGroup({ title }: { title: string }) {
  return <div className="sgroup">{title}</div>
}

function SItems({ items }: { items: NavItem[] }) {
  return (
    <>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => `sitem${isActive ? ' on' : ''}`}
        >
          <span className="ic"><item.icon className="w-4 h-4" /></span>
          <span className="lbl">{item.label}</span>
        </NavLink>
      ))}
    </>
  )
}

export function MainLayout() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()
  const isSuperadmin = user?.role === 'superadmin'

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="logo">
          <span className="logo-mark">{LOGO_MARK}</span>
          <span>
            <b>旗程</b>
            <span>AI 研发流程平台</span>
          </span>
        </div>

        <SItems items={NAV_TOP} />
        <SGroup title="项目管理" />
        <SItems items={NAV_PROJECT} />
        <SGroup title="知识" />
        <SItems items={NAV_KB} />

        {isSuperadmin && (
          <>
            <SGroup title="平台管理 · 仅超管" />
            <SItems items={NAV_ADMIN} />
          </>
        )}

        <div className="tour">
          <b>👤 {user?.nickname || user?.phone || '未登录'}</b>
          <span className="small muted">{isSuperadmin ? '超级管理员' : '普通用户'}</span>
          <button className="sitem" onClick={handleLogout}>
            <LogOut className="w-4 h-4 ic" />
            <span className="lbl">退出登录</span>
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="crumb" />
          <div className="top-actions">
            <button className="btn btn-ghost icon-btn" title="站内信">
              <Bell className="w-4 h-4" />
            </button>
            <button
              className="btn btn-ghost"
              style={{ gap: 8, padding: '3px 8px' }}
              onClick={handleLogout}
              title="个人信息 / 退出登录"
            >
              <span className="small nowrap"><b>{user?.nickname || user?.phone}</b> · {isSuperadmin ? '超管' : '用户'}</span>
            </button>
          </div>
        </header>
        <Outlet />
      </div>
    </div>
  )
}
