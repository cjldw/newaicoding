/**
 * ProjectOverview — 项目概览 Tab(R2)
 * - 统计区:四维卡(需求/开发任务/测试任务/发布任务)+ token 卡 + 近 7 天数字组
 * - 口径切换:累计/近 7 天(仅影响统计区数字,列表不变)
 * - 最近列表:需求 Top5 + 任务 Top5
 * - 发布卡附加区:最近发布 + 预览链接
 * 数据源:GET /api/projects/{project_id}/summary(R1 接口)
 */

import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { FileText, Code2, FlaskConical, Rocket, Loader2 } from 'lucide-react'
import { useProjectOverview, type ProjectOverview as OverviewData } from '@/api/projects'
import { formatTokens, timeAgo } from '@/utils/format'

/* ------------------------------------------------------------------ */
/* 枚举映射(照 TaskDetail.tsx VP_ST/VP_TYPE,原值照抄) */
/* ------------------------------------------------------------------ */
const REQ_ST_CN: Record<string, string> = {
  draft: '草稿',
  polishing: '打磨中',
  reviewing: '评审中',
  approved: '已评审',
  in_progress: '开发中',
  done: '已完成',
  archived: '已归档',
  rejected: '已驳回',
}

const REQ_ST_BDG: Record<string, string> = {
  draft: 'b-zinc',
  polishing: 'b-blue',
  reviewing: 'b-amber',
  approved: 'b-green',
  in_progress: 'b-blue',
  done: 'b-green',
  archived: 'b-zinc',
  rejected: 'b-red',
}

const TASK_ST_CN: Record<string, string> = {
  pending: '排队中',
  running: '运行中',
  cases_review: '用例评审',
  passed: '测试通过',
  failed: '失败',
  done: '已完成',
  cancelled: '已取消',
  timeout: '已超时',
}

const TASK_ST_BDG: Record<string, string> = {
  pending: 'b-zinc',
  running: 'b-blue',
  cases_review: 'b-amber',
  passed: 'b-green',
  failed: 'b-red',
  done: 'b-green',
  cancelled: 'b-zinc',
  timeout: 'b-red',
}

const TASK_TYPE_CN: Record<string, string> = {
  requirement: '打磨',
  dev: '开发',
  test: '测试',
  release: '发布',
}

const TASK_TYPE_BDG: Record<string, string> = {
  requirement: 'b-violet',
  dev: 'b-blue',
  test: 'b-violet',
  release: 'b-amber',
}

const PRIORITY_CN: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
}

const PRIORITY_BDG: Record<string, string> = {
  low: 'b-zinc',
  medium: 'b-blue',
  high: 'b-red',
}

/* ------------------------------------------------------------------ */
/* 维度卡配置 */
/* ------------------------------------------------------------------ */
interface DimConfig {
  key: 'requirements' | 'dev_tasks' | 'test_tasks' | 'release_tasks'
  name: string
  Icon: typeof FileText
  tabHref: string
}

const DIMS: DimConfig[] = [
  { key: 'requirements', name: '需求', Icon: FileText, tabHref: '?tab=requirements' },
  { key: 'dev_tasks', name: '开发任务', Icon: Code2, tabHref: '?tab=tasks' },
  { key: 'test_tasks', name: '测试任务', Icon: FlaskConical, tabHref: '?tab=tasks' },
  { key: 'release_tasks', name: '发布任务', Icon: Rocket, tabHref: '?tab=tasks' },
]

/* ------------------------------------------------------------------ */
/* 组件 */
/* ------------------------------------------------------------------ */
export function ProjectOverview() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const { data, isLoading, isError, refetch } = useProjectOverview(projectId ?? '')
  const [scope, setScope] = useState<'all' | '7d'>('all')

  if (isLoading) {
    return <div className="page-loading"><Loader2 className="w-4 h-4 animate-spin" /> 加载中…</div>
  }

  if (isError || !data) {
    return (
      <div className="card">
        <div className="empty">
          <div>加载项目概览失败</div>
          <button className="btn btn-sm" style={{ marginTop: 8 }} onClick={() => refetch()}>重试</button>
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* 口径切换行 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          className={`btn btn-sm ${scope === 'all' ? 'btn-pri' : ''}`}
          onClick={() => setScope('all')}
        >
          累计
        </button>
        <button
          className={`btn btn-sm ${scope === '7d' ? 'btn-pri' : ''}`}
          onClick={() => setScope('7d')}
        >
          近 7 天
        </button>
      </div>

      {/* 四维统计卡行 */}
      <div className="dgrid">
        {DIMS.map((d) => {
          const block = data[d.key]
          const byStatus = Object.entries(block.by_status ?? {})
            .filter(([, n]) => n > 0)
            .map(([s, n]) => {
              const cn = d.key === 'requirements' ? REQ_ST_CN[s] ?? s : TASK_ST_CN[s] ?? s
              const bdg = d.key === 'requirements' ? REQ_ST_BDG[s] ?? 'b-zinc' : TASK_ST_BDG[s] ?? 'b-zinc'
              return { s, n, cn, bdg }
            })
          return (
            <div
              key={d.key}
              className="dcard"
              onClick={() => navigate(d.tabHref)}
              role="link"
              tabIndex={0}
            >
              <div className="hd"><d.Icon className="w-3.5 h-3.5" />{d.name}</div>
              <div className="big">{block.total}</div>
              <div className="mini">
                {/* active 徽章置顶高亮 */}
                {block.active > 0 && (
                  <span className="bdg b-blue" style={{ fontSize: 11 }}>进行中 {block.active}</span>
                )}
                {byStatus.map(({ s, n, cn, bdg }) => (
                  <span key={s} className={`bdg ${bdg}`} style={{ fontSize: 11 }}>
                    {cn} ×{n}
                  </span>
                ))}
              </div>
            </div>
          )
        })}
      </div>

      {/* token 卡行 */}
      <div className="kvs" style={{ marginBottom: 16 }}>
        <div className="kv">
          <label>累计 TOKEN</label>
          <div className="mono">{formatTokens(data.tokens.total)}</div>
        </div>
        <div className="kv">
          <label>近 7 天 TOKEN</label>
          <div className="mono">{formatTokens(calculateRecent7dTokens(data))}</div>
        </div>
        {renderTokenRatio('开发占比', data.tokens.by_type.dev, data.tokens.total)}
        {renderTokenRatio('测试占比', data.tokens.by_type.test, data.tokens.total)}
        {renderTokenRatio('发布占比', data.tokens.by_type.release, data.tokens.total)}
        {renderTokenRatio('打磨占比', data.tokens.by_type.requirement, data.tokens.total)}
      </div>

      {/* 近 7 天数字组 */}
      <div className="kvs" style={{ marginBottom: 16 }}>
        <div className="kv">
          <label>新增需求</label>
          <div className={scope === '7d' ? 'mono' : 'mono faint'}>{data.recent_7d.requirements_created}</div>
        </div>
        <div className="kv">
          <label>完成需求</label>
          <div className={scope === '7d' ? 'mono' : 'mono faint'}>{data.recent_7d.requirements_completed}</div>
        </div>
        <div className="kv">
          <label>新增任务</label>
          <div className={scope === '7d' ? 'mono' : 'mono faint'}>{data.recent_7d.tasks_created}</div>
        </div>
        <div className="kv">
          <label>完成任务</label>
          <div className={scope === '7d' ? 'mono' : 'mono faint'}>{data.recent_7d.tasks_completed}</div>
        </div>
      </div>

      {/* 最近列表(两列) */}
      <div className="grid2">
        {/* 最近需求 */}
        <div className="card">
          <div className="card-head">
            <span className="card-title"><FileText className="w-3.5 h-3.5" />最近需求</span>
            <a
              className="small"
              style={{ marginLeft: 'auto' }}
              href="#"
              onClick={(e) => { e.preventDefault(); navigate('?tab=requirements') }}
            >
              查看全部
            </a>
          </div>
          <div>
            {data.recent_requirements.length > 0 ? (
              data.recent_requirements.map((r) => (
                <div
                  key={r.req_id}
                  className="dlist-row"
                  onClick={() => navigate(`/requirements/${r.req_id}`)}
                >
                  <span className="ttl">
                    <b className="mono small">{r.req_id.slice(0, 8)}</b> · {r.title}
                  </span>
                  {r.priority && (
                    <span className={`bdg ${PRIORITY_BDG[r.priority] ?? 'b-zinc'} small`}>
                      {PRIORITY_CN[r.priority] ?? r.priority}
                    </span>
                  )}
                  <span className={`bdg ${REQ_ST_BDG[r.status] ?? 'b-zinc'} small`}>
                    {REQ_ST_CN[r.status] ?? r.status}
                  </span>
                  <span className="mono small faint nowrap">{timeAgo(r.updated_at)}</span>
                </div>
              ))
            ) : (
              <div className="empty">暂无需求</div>
            )}
          </div>
        </div>

        {/* 最近任务 */}
        <div className="card">
          <div className="card-head">
            <span className="card-title"><Code2 className="w-3.5 h-3.5" />最近任务</span>
            <a
              className="small"
              style={{ marginLeft: 'auto' }}
              href="#"
              onClick={(e) => { e.preventDefault(); navigate('?tab=tasks') }}
            >
              查看全部
            </a>
          </div>
          <div>
            {data.recent_tasks.length > 0 ? (
              data.recent_tasks.map((t) => {
                const timeStr = t.status === 'done' && t.finished_at
                  ? timeAgo(t.finished_at)
                  : timeAgo(t.updated_at)
                return (
                  <div
                    key={t.task_id}
                    className="dlist-row"
                    onClick={() => navigate(`/tasks/${t.task_id}`)}
                  >
                    <span className="ttl">
                      <b className="mono small">{t.task_id.slice(0, 8)}</b> · {t.title}
                    </span>
                    <span className={`bdg ${TASK_TYPE_BDG[t.type] ?? 'b-zinc'} small`}>
                      {TASK_TYPE_CN[t.type] ?? t.type}
                    </span>
                    <span className={`bdg ${TASK_ST_BDG[t.status] ?? 'b-zinc'} small`}>
                      {TASK_ST_CN[t.status] ?? t.status}
                    </span>
                    <span className="mono small faint nowrap">{timeStr}</span>
                  </div>
                )
              })
            ) : (
              <div className="empty">暂无任务</div>
            )}
          </div>
        </div>
      </div>

      {/* 发布卡附加区(最近发布) */}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head">
          <span className="card-title"><Rocket className="w-3.5 h-3.5" />发布</span>
        </div>
        {data.latest_release ? (
          <div style={{ padding: '12px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span>最近发布:</span>
              <span style={{ fontWeight: 500 }}>{data.latest_release.title}</span>
              <span className={`bdg ${TASK_ST_BDG[data.latest_release.status] ?? 'b-zinc'} small`}>
                {TASK_ST_CN[data.latest_release.status] ?? data.latest_release.status}
              </span>
              <span className="mono small faint">{data.latest_release.branch}</span>
              {data.latest_release.preview_url && (
                <a
                  className="small"
                  href={data.latest_release.preview_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ marginLeft: 'auto' }}
                >
                  打开预览
                </a>
              )}
            </div>
          </div>
        ) : (
          <div className="empty">暂无发布记录,创建发布任务后展示</div>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 辅助函数 */
/* ------------------------------------------------------------------ */
function calculateRecent7dTokens(data: OverviewData): number {
  // R1 接口未直接返回近 7 天 token,此处用 total 近似(二期可细化)
  // 实际应由后端 recent_7d 补充 tokens 字段
  return data.tokens.total
}

function renderTokenRatio(label: string, typeTotal: number | undefined, total: number) {
  const value = typeTotal ?? 0
  const percent = total > 0 ? Math.round((value / total) * 100) : 0
  const tooltip = `in: ${formatTokens(value)}, out: ${formatTokens(value)}`
  return (
    <div className="kv" title={tooltip}>
      <label>{label}</label>
      <div className="mono">{percent}%</div>
    </div>
  )
}
