/**
 * Breadcrumb — 面包屑导航(admin-shell.md §1)
 *
 * 渲染规则(严格照抄 vp 原型):
 *   - 每个层级:可点击 → <a>(用 React Router <Link>),当前页 → <b>
 *   - 层级间插入 <span className="sep">/</span>
 *   - CSS 类(.crumb / .crumb b / .crumb .sep)已在 globals.css @layer components
 *
 * 路由映射(admin-shell.md §1.2):
 *   - 顶层页(/、/projects、/knowledge、/admin/runners):单级 <b>
 *   - /admin/*:平台管理 / X(平台管理无落地页,渲染为 <b>)
 *   - /manage/*:工作台 / 项目管理 / X(项目管理 → /projects)
 *   - 动态路由(projects/:id 等):简单两级回退
 */
import { useLocation, Link } from 'react-router-dom'

interface CrumbItem {
  label: string
  href?: string
}

/** 路由 → 面包屑层级映射(精确匹配表) */
const EXACT_MAP: Record<string, CrumbItem[]> = {
  '/': [{ label: '工作台' }],
  '/projects': [{ label: '项目列表' }],
  '/knowledge': [{ label: '知识条目' }],
  '/manage/requirements': [
    { label: '工作台', href: '/' },
    { label: '项目管理', href: '/projects' },
    { label: '需求管理' },
  ],
  '/manage/tasks': [
    { label: '工作台', href: '/' },
    { label: '项目管理', href: '/projects' },
    { label: '任务管理' },
  ],
  '/manage/tests': [
    { label: '工作台', href: '/' },
    { label: '项目管理', href: '/projects' },
    { label: '测试管理' },
  ],
  '/manage/releases': [
    { label: '工作台', href: '/' },
    { label: '项目管理', href: '/projects' },
    { label: '发布管理' },
  ],
  '/admin/runners': [{ label: '平台管理', href: '/admin/platform-settings' }, { label: 'Runner 管理' }],
  '/admin/users': [{ label: '平台管理', href: '/admin/platform-settings' }, { label: '用户管理' }],
  '/admin/audit-logs': [{ label: '平台管理', href: '/admin/platform-settings' }, { label: '审计日志' }],
  '/admin/platform-settings': [{ label: '平台管理', href: '/admin/platform-settings' }, { label: '平台设置' }],
  '/admin/skills': [{ label: '平台管理', href: '/admin/platform-settings' }, { label: 'Skills 管理' }],
}

/**
 * 根据 pathname 返回面包屑层级数组
 * 精确匹配优先;未命中时按前缀回退到动态路由;仍无则返回空(不渲染)
 */
function getBreadcrumbs(pathname: string): CrumbItem[] {
  // 精确匹配(去除尾部斜杠以兼容)
  const key = pathname === '/' ? '/' : pathname.replace(/\/$/, '')
  if (EXACT_MAP[key]) return EXACT_MAP[key]

  // 动态路由前缀匹配(早 return,不写 else)
  if (pathname.startsWith('/projects/create')) {
    return [{ label: '项目列表', href: '/projects' }, { label: '新建项目' }]
  }
  if (pathname.startsWith('/projects/')) {
    return [{ label: '项目列表', href: '/projects' }, { label: '项目详情' }]
  }
  if (pathname.startsWith('/requirements/')) {
    return [{ label: '需求详情' }]
  }
  if (pathname.startsWith('/tasks/')) {
    return [{ label: '任务详情' }]
  }

  // 未匹配:不渲染
  return []
}

export function Breadcrumb() {
  const { pathname } = useLocation()
  const items = getBreadcrumbs(pathname)

  if (items.length === 0) return null

  return (
    <>
      {items.map((item, i) => {
        const isLast = i === items.length - 1
        return (
          <span key={`${item.label}-${i}`} style={{ display: 'contents' }}>
            {i > 0 && <span className="sep">/</span>}
            {item.href && !isLast
              ? <Link to={item.href}>{item.label}</Link>
              : <b>{item.label}</b>}
          </span>
        )
      })}
    </>
  )
}
