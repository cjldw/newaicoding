/**
 * Dashboard — R21 工作台(vp 原型对齐)
 * - 四卡片(dcard)统计:需求/dev/test/release,「与我相关」口径(关联用户∪创建者,R7)
 * - 每类最近 5 条(dlist-row),点击进详情
 * - R7:行加交付徽章(已逾期 b-red / 明天截止 b-amber)+ running pulse dot;行动优先排序;零新视觉
 * - 无项目空态引导
 * 数据源:/api/dashboard/summary(R21 聚合接口)
 */

import { useNavigate } from 'react-router-dom'
import { FileText, Code2, FlaskConical, Rocket, Plus, FolderKanban, LayoutDashboard } from 'lucide-react'
import { useDashboardSummary } from '@/api/dashboard'
import type { DashboardBlock } from '@/api/dashboard'

const ST_CN: Record<string, string> = {
  draft: '草稿', polishing: '打磨中', reviewing: '评审中', approved: '已批准',
  in_progress: '进行中', done: '已完成', archived: '已归档', rejected: '已取消',
  pending: '待执行', running: '执行中', cases_review: '用例评审', passed: '通过',
  failed: '失败', cancelled: '已取消', timeout: '超时',
}

interface Dim {
  key: 'requirements' | 'dev' | 'test' | 'release'
  /** R7.F1(BUG-KB-006):summary 后端真实键(requirements/dev_tasks/test_tasks/release_tasks) */
  skey: 'requirements' | 'dev_tasks' | 'test_tasks' | 'release_tasks'
  name: string
  Icon: typeof FileText
  href: string
  rowHref: (id: string) => string
}

/** R7:recent 行(delivery_date 为后端并行透传,可选) */
interface RecentRow {
  task_id?: string
  req_id?: string
  title: string
  status: string
  project: { name?: string }
  updated_at?: string
  delivery_date?: string | null
}

// R7:终态集合(需求 done/archived/rejected;任务 done/archived/failed/cancelled/timeout/passed)——终态不标交付徽章
const TERMINAL_ST = new Set(['done', 'archived', 'rejected', 'failed', 'cancelled', 'timeout', 'passed'])
// R7:「运行中/待办」行动态(running/pending/reviewing/polishing),排序优先于普通行
const ACTIVE_ST = new Set(['running', 'pending', 'reviewing', 'polishing'])

// R7:「今天/明天」按 GMT+8(Asia/Shanghai)计算,与 R5 RequirementList.gmt8Today 同约定:
// now + 8h 后取 UTC 年月日即为 GMT+8 墙钟日期,输出 YYYY-MM-DD 与 delivery_date(DATE 串)直接字典序比较
function gmt8Date(offsetDays = 0): string {
  const gmt8 = new Date(Date.now() + 8 * 3600 * 1000 + offsetDays * 86400 * 1000)
  const y = gmt8.getUTCFullYear()
  const m = String(gmt8.getUTCMonth() + 1).padStart(2, '0')
  const d = String(gmt8.getUTCDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

// R7:行动优先级——已逾期 0 > 明天截止 1 > 运行中/待办状态 2 > 其他 3(同级内调用方再按更新时间倒序)
function actionRank(status: string, deliveryDate: string | null | undefined, today: string, tomorrow: string): number {
  if (deliveryDate && !TERMINAL_ST.has(status)) {
    if (deliveryDate < today) return 0
    if (deliveryDate === tomorrow) return 1
  }
  if (ACTIVE_ST.has(status)) return 2
  return 3
}

// R7:交付徽章(复用 R5 逾期判定口径)——已设日期且非终态:<今天 红已逾期,=明天 黄明天截止;否则不渲染
function DeliveryBadge({ row, today, tomorrow }: { row: RecentRow; today: string; tomorrow: string }) {
  if (!row.delivery_date || TERMINAL_ST.has(row.status)) return null
  if (row.delivery_date < today) return <span className="bdg b-red small">已逾期</span>
  if (row.delivery_date === tomorrow) return <span className="bdg b-amber small">明天截止</span>
  return null
}

const DIMS: Dim[] = [
  { key: 'requirements', skey: 'requirements', name: '需求', Icon: FileText, href: '/manage/requirements', rowHref: (id) => `/requirements/${id}` },
  { key: 'dev', skey: 'dev_tasks', name: '开发任务', Icon: Code2, href: '/manage/tasks', rowHref: (id) => `/tasks/${id}` },
  { key: 'test', skey: 'test_tasks', name: '测试任务', Icon: FlaskConical, href: '/manage/tests', rowHref: (id) => `/tasks/${id}` },
  { key: 'release', skey: 'release_tasks', name: '发布任务', Icon: Rocket, href: '/manage/releases', rowHref: (id) => `/tasks/${id}` },
]

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN')
}

export function Dashboard() {
  const nav = useNavigate()
  const { data: summary } = useDashboardSummary()
  // R21.F1(BUG-051):门槛与数据同源——summary 的 visible_projects(成员/owner 可见 active 项目),
  // 弃用 owner-only 的 /api/projects 口径(成员但非 owner 曾被误判「无项目」)
  const hasProject = (summary?.visible_projects ?? 0) > 0

  const cards = DIMS.map((d) => {
    const block: DashboardBlock = (summary as any)?.[d.skey] ?? { total: 0, by_status: {}, recent: [] }
    const by = Object.entries(block?.by_status ?? {})
      .filter(([, n]) => n > 0)
      .map(([s, n]) => `${ST_CN[s] ?? s} ×${n}`)
    return (
      <div key={d.key} className="dcard" onClick={() => nav(d.href)} role="link" tabIndex={0}>
        <div className="hd"><d.Icon className="w-3.5 h-3.5" />{d.name}</div>
        <div className="big">{block?.total ?? 0}</div>
        <div className="mini">
          {by.map((txt) => <span key={txt} className="bdg b-zinc" style={{ fontSize: 11 }}>{txt}</span>)}
        </div>
      </div>
    )
  })

  const lists = DIMS.map((d) => {
    const block: DashboardBlock = (summary as any)?.[d.skey] ?? { total: 0, by_status: {}, recent: [] }
    const rows = block.recent as RecentRow[]
    // R7:行动优先前端 resort(数据仍后端 recent 5 条)——已逾期 > 明天截止 > 运行中/待办 > 最近更新;同级更新时间倒序
    const today = gmt8Date()
    const tomorrow = gmt8Date(1)
    const sorted = rows
      .slice()
      .sort((a, b) => {
        const ra = actionRank(a.status, a.delivery_date, today, tomorrow)
        const rb = actionRank(b.status, b.delivery_date, today, tomorrow)
        if (ra !== rb) return ra - rb
        return (b.updated_at ?? '').localeCompare(a.updated_at ?? '')
      })
    const emptyText = d.key === 'requirements' ? '暂无需求,去创建第一个需求' : `暂无${d.name}`
    const idOf = (r: RecentRow) => r.task_id ?? r.req_id ?? ''
    return (
      <div className="card" key={d.key}>
        <div className="card-head">
          <span className="card-title"><d.Icon className="w-3.5 h-3.5" />{d.name} · 最近 5 条</span>
          <a className="small" style={{ marginLeft: 'auto' }} href={d.href}>
            查看全部
          </a>
        </div>
        <div>
          {sorted.length ? sorted.map((it) => (
            <div
              key={idOf(it)}
              className="dlist-row"
              onClick={() => nav(d.rowHref(idOf(it)))}
            >
              <span className="ttl"><b className="mono small">{idOf(it).slice(0, 8)}</b> · {it.title}</span>
              <span className="small muted nowrap">{it.project?.name || '—'}</span>
              {/* R7:running 行状态徽章内加 pulse dot(复用 TaskDetail StatusBadge / globals .dot.pulse 写法) */}
              <span className="bdg b-zinc small">
                {it.status === 'running' && <span className="dot pulse" />}
                {ST_CN[it.status] ?? it.status}
              </span>
              <DeliveryBadge row={it} today={today} tomorrow={tomorrow} />
              <span className="mono small faint nowrap">{fmtTime(it.updated_at)}</span>
            </div>
          )) : <div className="empty">{emptyText}</div>}
        </div>
      </div>
    )
  })

  return (
    <div className="page wide">
      <div className="page-head">
        <div>
          <h1 className="flex items-center gap-2"><LayoutDashboard size={18} /> 工作台</h1>
          <div className="sub">与我相关的四类数据 · 口径「关联用户∪创建者」+ 成员项目过滤,与四维管理菜单同源工具(R21/R7)</div>
        </div>
      </div>
      {hasProject ? (
        <>
          <div className="dgrid">{cards}</div>
          <div className="grid2">{lists}</div>
          <div className="small faint" style={{ marginTop: 12 }}>
            统计仅进入页面时拉取一次,不做实时刷新;变更感知走站内信 / toast(R18)。被移出项目后,该项目数据下次拉取起不再出现。
          </div>
        </>
      ) : (
        <div className="card">
          <div className="empty">
            <FolderKanban className="w-6 h-6 mx-auto" />
            <div style={{ marginTop: 8 }}>还没有项目 · 创建项目或等待邀请,开始你的第一个需求</div>
            <button className="btn btn-pri" style={{ margin: '10px auto 0' }} onClick={() => nav('/projects')}>
              <Plus className="w-4 h-4" /> 新建项目
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
