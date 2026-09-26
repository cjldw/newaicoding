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
 *   - 动态路由(projects/:id 等):前缀匹配 + 上下文覆盖
 *
 * 动态详情面包屑(BUG-UI-063):
 *   - 详情页通过 BreadcrumbOverrideProvider 设置动态 crumbs(用页面已加载数据)
 *   - 无覆盖时走增强前缀匹配(带完整父级链 + 类型标签兜底)
 */
import { useEffect, useState, type ReactNode } from 'react'
import { useLocation, Link } from 'react-router-dom'

export interface CrumbItem {
  label: string
  href?: string
}

/**
 * 供详情页设置面包屑(挂载时设置,卸载时清空)。
 * R4.F4:经模块级桥 `setCrumbsBridge` 投递给 Breadcrumb 实例 ——
 * 原 React Context 方案中 Provider 只包住 <Breadcrumb/> 自身,路由 Outlet 在
 * context 之外,详情页写到的永远是 default context(noop),覆盖从未生效。
 */
export function BreadcrumbOverrideProvider({ crumbs, children }: { crumbs: CrumbItem[]; children?: ReactNode }) {
  useEffect(() => {
    setCrumbsBridge?.(crumbs)
    return () => { setCrumbsBridge?.(null) }
  }, [crumbs])
  return <>{children}</>
}

/** 路由 → 面包屑层级映射(精确匹配表) */
const EXACT_MAP: Record<string, CrumbItem[]> = {
  '/': [{ label: '工作台' }],
  '/projects': [{ label: '工作台', href: '/' }, { label: '项目管理', href: '/projects' }, { label: '项目列表' }],
  '/knowledge': [{ label: '知识' }, { label: '知识条目' }],
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
  // /settings/* — 挂入 MainLayout 后补面包屑(「设置」无落地页,index 重定向到 profile,链接指向之)
  '/settings/profile': [{ label: '设置', href: '/settings/profile' }, { label: '个人资料' }],
  '/settings/gitlab-token': [{ label: '设置', href: '/settings/profile' }, { label: 'GitLab Token' }],
  '/settings/notifications': [{ label: '设置', href: '/settings/profile' }, { label: '通知设置' }],
}

/**
 * 根据 pathname 返回面包屑层级数组(增强前缀匹配,带完整父级链)
 * 精确匹配优先;未命中时按前缀回退到动态路由;仍无则返回空(不渲染)
 */
function getBreadcrumbs(pathname: string): CrumbItem[] {
  // 精确匹配(去除尾部斜杠以兼容)
  const key = pathname === '/' ? '/' : pathname.replace(/\/$/, '')
  if (EXACT_MAP[key]) return EXACT_MAP[key]

  // 动态路由前缀匹配(增强版:完整父级链 + ID 提取)
  // 项目新建
  if (pathname.startsWith('/projects/create')) {
    return [{ label: '项目列表', href: '/projects' }, { label: '新建项目' }]
  }
  // 知识库视图: /projects/:projectId/knowledge-bases/:kbId
  const kbViewMatch = pathname.match(/^\/projects\/([^/]+)\/knowledge-bases\/([^/]+)/)
  if (kbViewMatch) {
    return [
      { label: '知识条目', href: '/knowledge' },
      { label: '知识库' }, // 兜底,详情页会用 context 覆盖为 kb.name
    ]
  }
  // 知识库列表: /projects/:projectId/knowledge-bases
  if (pathname.match(/^\/projects\/([^/]+)\/knowledge-bases\/?$/)) {
    return [
      { label: '项目列表', href: '/projects' },
      { label: '项目详情' }, // 兜底,详情页会用 context 覆盖
      { label: '知识库' },
    ]
  }
  // 项目知识库(旧路由): /projects/:projectId/knowledge
  if (pathname.match(/^\/projects\/([^/]+)\/knowledge\/?$/)) {
    return [
      { label: '知识条目', href: '/knowledge' },
    ]
  }
  // 项目需求列表: /projects/:projectId/requirements
  if (pathname.match(/^\/projects\/([^/]+)\/requirements\/?$/)) {
    return [
      { label: '项目列表', href: '/projects' },
      { label: '项目详情' }, // 兜底
      { label: '需求' },
    ]
  }
  // 项目详情: /projects/:projectId
  const projMatch = pathname.match(/^\/projects\/([^/]+)\/?$/)
  if (projMatch) {
    return [
      { label: '项目列表', href: '/projects' },
      { label: '项目详情' }, // 兜底,详情页会用 context 覆盖为 project.name
    ]
  }
  // 归档页: /requirements/:reqId/archive(R33.F7:补完整父级链,与需求详情同构)
  const archiveMatch = pathname.match(/^\/requirements\/([^/]+)\/archive\/?$/)
  if (archiveMatch) {
    return [
      { label: '项目管理', href: '/projects' },
      { label: '需求', href: `/requirements/${archiveMatch[1]}` },
      { label: '归档' },
    ]
  }
  // 需求详情: /requirements/:reqId
  if (pathname.match(/^\/requirements\/([^/]+)\/?$/)) {
    return [
      { label: '项目管理', href: '/projects' },
      { label: '需求' },
      { label: '需求详情' }, // 兜底,详情页会用 context 覆盖为 requirement.title
    ]
  }
  // 任务子页: /tasks/:taskId/cases
  const taskCasesMatch = pathname.match(/^\/tasks\/([^/]+)\/cases\/?$/)
  if (taskCasesMatch) {
    return [
      { label: '项目管理', href: '/projects' },
      { label: '任务' },
      { label: '用例审阅' },
    ]
  }
  // 任务子页: /tasks/:taskId/report
  const taskReportMatch = pathname.match(/^\/tasks\/([^/]+)\/report\/?$/)
  if (taskReportMatch) {
    return [
      { label: '项目管理', href: '/projects' },
      { label: '任务' },
      { label: '测试报告' },
    ]
  }
  // 任务子页: /tasks/:taskId/deploy
  const taskDeployMatch = pathname.match(/^\/tasks\/([^/]+)\/deploy\/?$/)
  if (taskDeployMatch) {
    return [
      { label: '项目管理', href: '/projects' },
      { label: '任务' },
      { label: '部署状态' },
    ]
  }
  // 任务详情: /tasks/:taskId
  if (pathname.match(/^\/tasks\/([^/]+)\/?$/)) {
    return [
      { label: '项目管理', href: '/projects' },
      { label: '任务' },
      { label: '任务详情' }, // 兜底,详情页会用 context 覆盖为 task.title
    ]
  }

  // 未匹配:不渲染
  return []
}

function BreadcrumbInner() {
  const { pathname } = useLocation()
  // R4.F4 修正:override 改走模块级桥。原 BreadcrumbProvider 只包住 <Breadcrumb/> 自身,
  // Outlet 在 context 之外,详情页的 BreadcrumbOverrideProvider 写到的是 default context(noop),
  // 覆盖从未真正生效(此前 9 页核对验的是 pattern 兜底链,掩盖了该缺陷)。
  const [overrideCrumbs, setOverrideCrumbs] = useState<CrumbItem[] | null>(null)
  useEffect(() => {
    // Breadcrumb 先于路由子页面挂载(MainLayout 中为前置兄弟),注册时子页 effect 尚未运行,时序安全
    setCrumbsBridge = setOverrideCrumbs
    return () => { setCrumbsBridge = null }
  }, [])
  // 优先用覆盖(详情页动态数据),否则走 pattern 匹配
  const items = overrideCrumbs ?? getBreadcrumbs(pathname)

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

/** 模块级桥:详情页 override → Breadcrumb 实例(跨子树生效) */
let setCrumbsBridge: ((c: CrumbItem[] | null) => void) | null = null

export function Breadcrumb() {
  return <BreadcrumbInner />
}
