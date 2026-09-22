/**
 * Dashboard — R21 工作台(vp 原型对齐)
 * - 四卡片(dcard)统计:需求/dev/test/release,created_by=me 口径
 * - 每类最近 5 条(dlist-row),点击进详情
 * - 无项目空态引导
 * 数据源:/api/dashboard/summary(R21 聚合接口)
 */

import { useNavigate } from 'react-router-dom'
import { FileText, Code2, FlaskConical, Rocket, Plus, FolderKanban } from 'lucide-react'
import { useDashboardSummary } from '@/api/dashboard'
import { useProjectList } from '@/api/projects'
import type { DashboardBlock } from '@/api/dashboard'

const ST_CN: Record<string, string> = {
  draft: '草稿', polishing: '打磨中', reviewing: '评审中', approved: '已批准',
  in_progress: '进行中', done: '已完成', archived: '已归档', rejected: '已取消',
  pending: '待执行', running: '执行中', cases_review: '用例评审', passed: '通过',
  failed: '失败', cancelled: '已取消', timeout: '超时',
}

interface Dim {
  key: 'requirements' | 'dev' | 'test' | 'release'
  name: string
  Icon: typeof FileText
  href: string
  rowHref: (id: string) => string
}

const DIMS: Dim[] = [
  { key: 'requirements', name: '需求', Icon: FileText, href: '/manage/requirements', rowHref: (id) => `/requirements/${id}` },
  { key: 'dev', name: '开发任务', Icon: Code2, href: '/manage/tasks', rowHref: (id) => `/tasks/${id}` },
  { key: 'test', name: '测试任务', Icon: FlaskConical, href: '/manage/tests', rowHref: (id) => `/tasks/${id}` },
  { key: 'release', name: '发布任务', Icon: Rocket, href: '/manage/releases', rowHref: (id) => `/tasks/${id}` },
]

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN')
}

export function Dashboard() {
  const nav = useNavigate()
  const { data: summary } = useDashboardSummary()
  const { data: projects } = useProjectList({})
  const hasProject = (projects?.total ?? 0) > 0

  const cards = DIMS.map((d) => {
    const block: DashboardBlock = (summary as any)?.[d.key] ?? { total: 0, by_status: {}, recent: [] }
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
    const block: DashboardBlock = (summary as any)?.[d.key] ?? { total: 0, by_status: {}, recent: [] }
    const rows = block.recent as { task_id?: string; req_id?: string; title: string; status: string; project: { name?: string }; updated_at?: string }[]
    const emptyText = d.key === 'requirements' ? '暂无需求,去创建第一个需求' : `暂无${d.name}`
    const idOf = (r: { task_id?: string; req_id?: string }) => r.task_id ?? r.req_id ?? ''
    return (
      <div className="card" key={d.key}>
        <div className="card-head">
          <span className="card-title"><d.Icon className="w-3.5 h-3.5" />{d.name} · 最近 5 条</span>
          <a className="small" style={{ marginLeft: 'auto' }} href={d.href}>
            查看全部
          </a>
        </div>
        <div>
          {rows.length ? rows.map((it) => (
            <div
              key={idOf(it)}
              className="dlist-row"
              onClick={() => nav(d.rowHref(idOf(it)))}
            >
              <span className="ttl"><b className="mono small">{idOf(it).slice(0, 8)}</b> · {it.title}</span>
              <span className="small muted nowrap">{it.project?.name || '—'}</span>
              <span className="bdg b-zinc small">{ST_CN[it.status] ?? it.status}</span>
              <span className="mono small faint nowrap">{fmtTime(it.updated_at)}</span>
            </div>
          )) : <div className="empty">{emptyText}</div>}
        </div>
      </div>
    )
  })

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>工作台</h1>
          <div className="sub">与我相关的四类数据 · 口径「我创建的」(created_by=me)+ 成员项目过滤,与四维管理菜单同源工具(R21)</div>
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
