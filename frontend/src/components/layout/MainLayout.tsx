/**
 * MainLayout — 主布局(R19/R20 对齐 vp 原型外壳)
 * - .shell: 220px 侧边栏(.sidebar:.logo/.sgroup/.sitem)+ .main(.topbar + Outlet)
 * - 侧栏分组: 顶部(工作台)/ 项目管理(列表+四维)/ 知识(知识条目+知识库)/ 平台管理·仅超管
 * - 顶栏: 面包屑 + .top-actions(铃铛 + 用户按钮[头像+姓名+角色徽章]+下拉)
 * - 用户信息从侧栏底部迁移到 topbar 右上(对齐 vp 原型)
 */

import { useRef, useEffect, useState, type MouseEvent } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, FolderKanban, ListChecks, Activity, FlaskConical, Rocket,
  BookOpen, Server, Users, ScrollText, Settings, Bell, LogOut, Blocks,
  ExternalLink, CheckCheck, Loader2,
} from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { Breadcrumb } from './Breadcrumb'
import { useUnreadCount, useNotificationList, useMarkNotificationRead, useMarkAllRead } from '@/api/notifications'

function LogoMark({ size = 17 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden style={{ display: 'block' }}>
      <rect x="7.2" y="6" width="2.6" height="21" rx="1.3" fill="#ffffff" />
      <path d="M10.4 7.6 24 13.2 10.4 13.2Z" fill="#3b82f6" />
      <path d="M10.4 13.2H24l-7 2.9h-6.6Z" fill="#d4d4d8" />
      <path d="M10.4 16.1h6.6L10.4 19Z" fill="#a1a1aa" />
    </svg>
  )
}

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
  { to: '/admin/skills', label: 'Skills 市场', icon: Blocks },
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
          <span className="ic"><item.icon size={15} /></span>
          <span className="lbl">{item.label}</span>
        </NavLink>
      ))}
    </>
  )
}

/** 头像背景色:按用户名/姓名首字映射(对齐 vp 原型) */
const AV_COLORS: Record<string, string> = {
  luowen: '#3b82f6', wangq: '#ec4899', liming: '#10b981',
  zhangy: '#f59e0b', chenx: '#8b5cf6',
}
function getAvColor(name?: string): string {
  if (!name) return '#6b7280'
  const key = name.toLowerCase()
  for (const k of Object.keys(AV_COLORS)) {
    if (key.includes(k)) return AV_COLORS[k]
  }
  // 按首字符 hash 取色
  const palette = ['#3b82f6', '#ec4899', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4']
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0x7fffffff
  return palette[h % palette.length]
}

/** 姓名首字(头像用) */
function getInitial(name?: string | null): string {
  if (!name) return '?'
  return name.charAt(0)
}

/** 角色徽章文案 + 样式 */
function getRoleBadge(role?: string): { label: string; cls: string } | null {
  if (role === 'superadmin') return { label: '超管', cls: 'bdg b-violet' }
  if (role) return { label: role, cls: 'bdg b-blue' }
  return null
}

export function MainLayout() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()
  const isSuperadmin = user?.role === 'superadmin'
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const userBtnRef = useRef<HTMLDivElement>(null)
  const [bellOpen, setBellOpen] = useState(false)
  const bellRef = useRef<HTMLDivElement>(null)

  // 通知数据:未读数(60s 轮询)+ 最近 5 条
  const { data: unreadData } = useUnreadCount()
  const { data: recentData, isLoading: recentLoading } = useNotificationList({ page: 1, page_size: 5 })
  const markRead = useMarkNotificationRead()
  const markAllRead = useMarkAllRead()

  const unreadCount = unreadData?.unread_count ?? 0
  const recentItems = recentData?.items ?? []

  // 点击外部关闭用户下拉
  useEffect(() => {
    if (!userMenuOpen) return
    function handleClick(e: globalThis.MouseEvent) {
      if (userBtnRef.current && !userBtnRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [userMenuOpen])

  // 点击外部关闭铃铛下拉
  useEffect(() => {
    if (!bellOpen) return
    function handleClick(e: globalThis.MouseEvent) {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) {
        setBellOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [bellOpen])

  function handleLogout() {
    logout()
    navigate('/login')
  }

  function handleUserBtnClick(e: MouseEvent) {
    e.stopPropagation()
    setUserMenuOpen((v) => !v)
  }

  function handleBellClick(e: MouseEvent) {
    e.stopPropagation()
    setBellOpen((v) => !v)
  }

  async function handleBellMarkAllRead() {
    try { await markAllRead.mutateAsync() } catch { /* 静默 */ }
  }

  async function handleBellItemClick(id: string, link: string | null) {
    if (link) navigate(link)
    setBellOpen(false)
    try { await markRead.mutateAsync(id) } catch { /* 静默 */ }
  }

  /** 相对时间(铃铛下拉用,简短) */
  function shortTime(dateStr: string): string {
    const diff = Date.now() - new Date(dateStr).getTime()
    const mins = Math.floor(diff / 60_000)
    if (mins < 1) return '刚刚'
    if (mins < 60) return `${mins}分钟前`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours}小时前`
    return `${Math.floor(hours / 24)}天前`
  }

  const displayName = user?.nickname || user?.phone || '未登录'
  const avColor = getAvColor(user?.nickname || user?.phone || undefined)
  const roleBadge = getRoleBadge(user?.role)

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="logo">
          <span className="logo-mark"><LogoMark size={17} /></span>
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

        {/* 侧栏底部:平台导览(对齐 vp 原型 .tour,不再放用户信息) */}
        <div className="tour">
          <b className="small">平台导览</b>
          <div className="small muted">首次使用?花 2 分钟了解四维管理与任务工作台…</div>
          <button className="btn btn-sm" style={{ marginTop: 8 }}>开始导览</button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="crumb"><Breadcrumb /></div>
          <div className="top-actions">
            {/* 站内信铃铛:未读徽章 + 下拉最近通知 + 查看全部 */}
            <div className="user-btn-wrap" ref={bellRef} style={{ position: 'relative' }}>
              <button
                className="btn btn-ghost icon-btn"
                title="站内信"
                onClick={handleBellClick}
                style={{ position: 'relative' }}
              >
                <Bell size={15} />
                {unreadCount > 0 && (
                  <span style={{
                    position: 'absolute', top: 2, right: 2,
                    minWidth: 14, height: 14, padding: '0 3px',
                    fontSize: 10, fontWeight: 600, lineHeight: '14px',
                    color: '#fff', background: '#ef4444',
                    borderRadius: 7, textAlign: 'center',
                  }}>
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
              </button>
              {bellOpen && (
                <div style={{
                  position: 'absolute', top: '100%', right: 0, marginTop: 4,
                  width: 320, background: 'var(--card-bg, #fff)',
                  border: '1px solid var(--border, #e4e4e7)',
                  borderRadius: 'var(--vp-radius, 8px)',
                  boxShadow: '0 4px 16px rgba(0,0,0,.1)',
                  zIndex: 100, overflow: 'hidden',
                }}>
                  <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '10px 12px', borderBottom: '1px solid var(--border, #e4e4e7)',
                  }}>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>通知</span>
                    {unreadCount > 0 && (
                      <button
                        onClick={handleBellMarkAllRead}
                        style={{
                          fontSize: 12, color: 'var(--primary, #3b82f6)',
                          background: 'none', border: 'none', cursor: 'pointer',
                          display: 'flex', alignItems: 'center', gap: 3,
                        }}
                      >
                        <CheckCheck size={12} /> 全部已读
                      </button>
                    )}
                  </div>
                  <div style={{ maxHeight: 280, overflowY: 'auto' }}>
                    {recentLoading ? (
                      <div style={{ padding: 20, textAlign: 'center' }}>
                        <Loader2 size={16} className="animate-spin" style={{ margin: '0 auto' }} />
                      </div>
                    ) : recentItems.length === 0 ? (
                      <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted, #a1a1aa)', fontSize: 13 }}>
                        暂无通知
                      </div>
                    ) : (
                      recentItems.map((item) => (
                        <div
                          key={item.notification_id}
                          onClick={() => handleBellItemClick(item.notification_id, item.link)}
                          style={{
                            padding: '10px 12px', cursor: 'pointer',
                            borderBottom: '1px solid var(--border, #f0f0f0)',
                            opacity: item.read_at ? 0.55 : 1,
                            display: 'flex', gap: 8, alignItems: 'flex-start',
                          }}
                        >
                          {!item.read_at && (
                            <span className="dot pulse" style={{
                              background: 'var(--primary, #3b82f6)', flexShrink: 0, marginTop: 5,
                            }} />
                          )}
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{
                              fontSize: 13, fontWeight: item.read_at ? 400 : 500,
                              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                            }}>
                              {item.title}
                            </div>
                            <div style={{ fontSize: 11, color: 'var(--text-muted, #a1a1aa)', marginTop: 2 }}>
                              {shortTime(item.created_at)}
                              {item.link && <ExternalLink size={10} style={{ marginLeft: 4, opacity: 0.4 }} />}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                  <div
                    onClick={() => { navigate('/notifications'); setBellOpen(false) }}
                    style={{
                      padding: '10px 12px', textAlign: 'center', fontSize: 13,
                      color: 'var(--primary, #3b82f6)', cursor: 'pointer',
                      borderTop: '1px solid var(--border, #e4e4e7)',
                    }}
                  >
                    查看全部通知
                  </div>
                </div>
              )}
            </div>

            {/* 用户按钮:头像[姓名首字]+姓名+角色徽章,下拉含退出登录 */}
            <div className="user-btn-wrap" ref={userBtnRef}>
              <button className="user-btn" onClick={handleUserBtnClick} type="button">
                <span className="av" style={{ background: avColor }}>{getInitial(displayName)}</span>
                <span>{displayName}</span>
                {roleBadge && <span className={roleBadge.cls}>{roleBadge.label}</span>}
              </button>
              {userMenuOpen && (
                <div className="user-menu">
                  <button
                    className="user-menu-item"
                    onClick={() => { setUserMenuOpen(false); handleLogout() }}
                  >
                    <LogOut size={15} />
                    <span>退出登录</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <Outlet />
      </div>
    </div>
  )
}
