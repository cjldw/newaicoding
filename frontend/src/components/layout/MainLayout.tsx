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
  ExternalLink, CheckCheck, Loader2, Play, Sun, Moon,
} from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { getAvColor, getInitial } from '@/utils/avatar'
import { Breadcrumb } from './Breadcrumb'
import { useUnreadCount, useNotificationList, useMarkNotificationRead, useMarkAllRead } from '@/api/notifications'
import { TourDialog, isTourCompleted } from '@/components/TourDialog'
import { useTheme } from '@/hooks/useTheme'

import { OrangeMark } from '@/components/OrangeMark'

// 品牌 Logo「旗橙」:橙子图标(OrangeMark);侧栏深色方块底由 .logo-mark 容器提供

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
  // R28:头像图加载失败时回退首字母;avatar_url 变化(上传/移除)后重置
  const [avatarError, setAvatarError] = useState(false)
  // R29:平台导览弹窗开关(条件渲染 TourDialog,open 时才挂载/发请求)
  const [tourOpen, setTourOpen] = useState(false)
  // R30:黑白主题(挂载即写 <html data-theme>;顶栏按钮切换,localStorage 持久化)
  const { theme, toggle: toggleTheme } = useTheme()

  useEffect(() => {
    setAvatarError(false)
  }, [user?.avatar_url])

  // R29:首次登录自动弹出导览——localStorage 无 tour_completed 标记则打开;
  // 完成/跳过后写入标记不再弹出;遮罩关闭不写标记,下次登录仍会弹出(分片控件联动)
  useEffect(() => {
    if (!isTourCompleted()) setTourOpen(true)
  }, [])

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
          <span className="logo-mark"><OrangeMark size={17} /></span>
          <span>
            <b>旗橙</b>
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

        {/* 侧栏底部:平台导览(对齐 vp 原型 .tour,不再放用户信息);常驻入口,无论是否已完成均可手动打开 */}
        <div className="tour">
          <b className="small"><Play size={12} style={{ verticalAlign: '-2px', marginRight: 4 }} />平台导览</b>
          <div className="small muted">首次使用?花 2 分钟了解四维管理与任务工作台…</div>
          <button className="btn btn-sm" style={{ marginTop: 8 }} onClick={() => setTourOpen(true)}>开始导览</button>
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
                  width: 320, background: 'var(--surface)',
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

            {/* R30:主题切换按钮(铃铛后,32×32 icon-btn;亮显 Moon/暗显 Sun,React 状态驱动图标切换) */}
            <button
              type="button"
              className="btn btn-ghost icon-btn"
              title={theme === 'light' ? '切换到暗色主题' : '切换到亮色主题'}
              onClick={toggleTheme}
              style={{ marginLeft: 8 }}
            >
              {theme === 'light' ? <Moon size={15} /> : <Sun size={15} />}
            </button>

            {/* 用户按钮:头像[姓名首字]+姓名+角色徽章,下拉含退出登录 */}
            <div className="user-btn-wrap" ref={userBtnRef}>
              <button className="user-btn" onClick={handleUserBtnClick} type="button">
                {/* R28:有 avatar_url 渲染圆形头像图(28px,object-fit:cover),失败/无头像回退首字母+hash 取色 */}
                {user?.avatar_url && !avatarError ? (
                  <img
                    className="av"
                    src={user.avatar_url}
                    alt={displayName}
                    style={{ objectFit: 'cover' }}
                    onError={() => setAvatarError(true)}
                  />
                ) : (
                  <span className="av" style={{ background: avColor }}>{getInitial(displayName)}</span>
                )}
                <span>{displayName}</span>
                {roleBadge && <span className={roleBadge.cls}>{roleBadge.label}</span>}
              </button>
              {userMenuOpen && (
                <div className="user-menu">
                  {/* R28.F1(BUG-040):个人设置入口——头像编辑/资料/GitLab Token/通知设置唯一可达路径 */}
                  <button
                    className="user-menu-item"
                    onClick={() => { setUserMenuOpen(false); navigate('/settings/profile') }}
                  >
                    <Settings size={15} />
                    <span>个人设置</span>
                  </button>
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

      {/* R29:平台导览弹窗(条件挂载,open 时才拉取步骤数据) */}
      {tourOpen && <TourDialog onClose={() => setTourOpen(false)} />}
    </div>
  )
}
