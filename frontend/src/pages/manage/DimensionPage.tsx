/**
 * 四维管理通用页面组件
 * 支持 requirements/dev/test/release 四个维度
 * R22.F2(BUG-UI-069):统一 audit-logs/vp pageManage 范式——page-head(带快速创建按钮)
 * + card(fbar 筛选区 → scrollx>tbl 表格区 → card-foot 说明);各维列定义照抄 vp L1665-1680;
 * 收敛 BUG-UI-052/053/054/055/059/060/061/062
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { LucideIcon } from 'lucide-react'
import {
  Plus, Shield, ChevronRight, GitBranch, Folder, FlaskConical,
} from 'lucide-react'
import { useDimensionList, type DimensionItem } from '@/api/dashboard'
import { useProjectList } from '@/api/projects'
import { requirementsApi } from '@/api/requirements'
import { createTask, type CreateTaskPayload } from '@/api/tasks'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/Dialog'
import { Alert } from '@/components/ui/Alert'

interface StatusOption {
  value: string
  label: string
}

interface DimensionPageProps {
  dimension: 'requirements' | 'dev' | 'test' | 'release'
  title: string
  statusOptions: StatusOption[]
  /** 页头标题图标(vp pageManage 的 conf.icn) */
  icon?: LucideIcon
  /** 页头标题下方说明行(vp pageManage 的 conf.desc) */
  desc?: string
  /** 快速创建按钮文案(vp conf.createLabel,如"新建需求") */
  createLabel?: string
}

// 任务类型徽章色(与 vp TYPE 映射一致:打磨 blue/开发 violet/测试 amber/发布 green)
const TYPE_BADGE: Record<string, { label: string; cls: string }> = {
  requirement: { label: '打磨', cls: 'b-blue' },
  dev: { label: '开发', cls: 'b-violet' },
  test: { label: '测试', cls: 'b-amber' },
  release: { label: '发布', cls: 'b-green' },
}

// 优先级徽章(vp requirements 行:high 红/medium 琥珀/low zinc)
const PRIORITY_BADGE: Record<string, { label: string; cls: string }> = {
  high: { label: '高', cls: 'b-red' },
  medium: { label: '中', cls: 'b-amber' },
  low: { label: '低', cls: 'b-zinc' },
}

// 快速创建对话框标题文案(vp names[dim]:dev 维显示"新建开发任务",页头按钮用 conf.createLabel)
const QUICK_DIALOG_NAME: Record<DimensionPageProps['dimension'], string> = {
  requirements: '新建需求',
  dev: '新建开发任务',
  test: '新建测试任务',
  release: '新建发布任务',
}

// 各维表头(照抄 vp conf.heads 一字不差;末列为 chevron 空表头)
const HEADS: Record<DimensionPageProps['dimension'], string[]> = {
  requirements: ['需求', '所属项目', '状态', '优先级', '需求分支', '创建人', '更新时间'],
  dev: ['任务', '所属项目', '类型', '状态', 'Runner', '创建人', '更新时间'],
  test: ['测试任务', '所属项目', '状态', '用例通过', '创建人', '更新时间'],
  release: ['发布任务', '所属项目', '状态', '部署 URL', '端口', '创建人', '更新时间'],
}

export function DimensionPage({ dimension, title, statusOptions, icon: Icon, desc, createLabel }: DimensionPageProps) {
  const navigate = useNavigate()
  const [status, setStatus] = useState<string>('')
  const [projectId, setProjectId] = useState<string>('')
  const [q, setQ] = useState<string>('')
  // 受控输入与提交值分离:回车/失焦才提交(vp"搜索标题,回车确认"语义)
  const [qInput, setQInput] = useState<string>('')
  const [page, setPage] = useState(1)
  const [quickOpen, setQuickOpen] = useState(false)
  const pageSize = 20

  const { data, isLoading } = useDimensionList(dimension, {
    status: status || undefined,
    project_id: projectId || undefined,
    q: q || undefined,
    page,
    page_size: pageSize,
  })

  const handleRowClick = (item: DimensionItem) => {
    // 根据维度跳转到对应详情页
    if (dimension === 'requirements') {
      navigate(`/requirements/${item.key}`)
    } else {
      navigate(`/tasks/${item.key}`)
    }
  }

  const submitQ = () => {
    const next = qInput.trim()
    if (next !== q) {
      setQ(next)
      setPage(1)
    }
  }

  const totalPages = data ? Math.ceil(data.total / pageSize) : 1
  const heads = HEADS[dimension]

  return (
    <div className="page wide">
      <div className="page-head">
        <div>
          {/* vp pageManage 结构:icon + 标题,换行,说明(sub) */}
          <h1 className="flex items-center gap-2">
            {Icon && <Icon size={18} />}
            {title}
          </h1>
          {desc && <div className="sub">{desc}</div>}
        </div>
        {/* R22.F2(BUG-UI-061):右上角快速创建按钮(样式对齐 admin/runners) */}
        {createLabel && (
          <div className="acts">
            <button className="btn btn-pri" onClick={() => setQuickOpen(true)}>
              <Plus className="w-4 h-4" />
              {createLabel}(快速创建)
            </button>
          </div>
        )}
      </div>

      {/* audit-logs 范式(BUG-UI-052/062):fbar 筛选区与表格区同在 .card 内、上下分层 */}
      <div className="card">
        <div className="fbar">
          <ProjectFilter value={projectId} onChange={(v) => { setProjectId(v); setPage(1) }} />
          <select
            className="input"
            value={status}
            onChange={(e) => { setStatus(e.target.value); setPage(1) }}
          >
            <option value="">全部状态</option>
            {statusOptions.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          {/* BUG-UI-053:搜索框 */}
          <input
            className="input grow"
            placeholder="搜索标题,回车确认"
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submitQ() }}
            onBlur={submitQ}
          />
          {/* 统计文案:fbar 右侧(照抄 vp) */}
          <span className="small faint" style={{ marginLeft: 'auto' }}>
            共 {data?.total ?? 0} 条 · updated_at 倒序 · 20/页
          </span>
        </div>

        <div className="scrollx">
          <table className="tbl">
            <thead>
              <tr>
                {heads.map(h => <th key={h}>{h}</th>)}
                <th></th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={heads.length + 1} className="empty">加载中...</td></tr>
              ) : !data || data.items.length === 0 ? (
                <tr><td colSpan={heads.length + 1} className="empty">暂无数据 · 调整筛选或快速创建</td></tr>
              ) : (
                data.items.map(item => (
                  <tr key={item.key} className="rowclick" onClick={() => handleRowClick(item)}>
                    <DimensionCells dimension={dimension} item={item} statusOptions={statusOptions} />
                    <td><ChevronRight size={14} /></td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="card-foot" style={{ justifyContent: 'center' }}>
            <button
              className="btn btn-sm"
              disabled={page <= 1}
              onClick={() => setPage(p => Math.max(1, p - 1))}
            >
              上一页
            </button>
            <span className="muted small">
              第 {page} / {totalPages} 页,共 {data?.total ?? 0} 条
            </span>
            <button
              className="btn btn-sm"
              disabled={page >= totalPages}
              onClick={() => setPage(p => p + 1)}
            >
              下一页
            </button>
          </div>
        )}

        {/* vp L1705 脚注 */}
        <div className="card-foot">
          <Shield size={13} />
          归档 / 软删项目数据不出现;viewer 只读(新建按钮隐藏,API 写操作 403 前后端双重拦截)
        </div>
      </div>

      {createLabel && (
        <QuickCreateDialog
          open={quickOpen}
          dimension={dimension}
          createLabel={createLabel}
          onClose={() => setQuickOpen(false)}
        />
      )}
    </div>
  )
}

/** 项目筛选下拉(全部项目 + 我有权限的项目;可见口径与后端 _visible_project_ids 一致) */
function ProjectFilter({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data } = useProjectList({ status: 'active', page: 1, page_size: 100 })
  const items = data?.items ?? []
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">全部项目</option>
      {items.map(p => (
        <option key={p.project_id} value={p.project_id}>{p.name}</option>
      ))}
    </select>
  )
}

/** 各维列渲染(照抄 vp requirements/tasks/tests/releases cells 顺序与样式) */
function DimensionCells({
  dimension, item, statusOptions,
}: {
  dimension: DimensionPageProps['dimension']
  item: DimensionItem
  statusOptions: StatusOption[]
}) {
  const entityCell = <td><b>{item.key.slice(0, 8)}</b> · {item.title}</td>
  const projCell = (
    <td><span className="chip"><Folder size={11} style={{ display: 'inline', verticalAlign: '-1px' }} /> {item.project.name}</span></td>
  )
  const stCell = (
    <td>
      <span className={`bdg b-${getStatusColor(item.status)}`}>
        {getStatusText(item.status, statusOptions)}
      </span>
    </td>
  )
  const userCell = (
    <td><span className="small">{item.created_by?.nickname || item.created_by?.username || '—'}</span></td>
  )
  const timeCell = <td className="mono small muted" style={{ whiteSpace: 'nowrap' }}>{formatDate(item.updated_at)}</td>

  // BUG-UI-059:需求维优先级/需求分支列
  if (dimension === 'requirements') {
    const pri = PRIORITY_BADGE[item.priority || 'medium']
    return (
      <>
        {entityCell}
        {projCell}
        {stCell}
        <td><span className={`bdg ${pri.cls}`}>{pri.label}</span></td>
        <td><span className="chip"><GitBranch size={12} style={{ display: 'inline', verticalAlign: '-1px' }} /> {item.req_branch || '—'}</span></td>
        {userCell}
        {timeCell}
      </>
    )
  }
  // BUG-UI-060:任务维类型/Runner 列
  if (dimension === 'dev') {
    const tp = item.type ? TYPE_BADGE[item.type] : undefined
    return (
      <>
        {entityCell}
        {projCell}
        <td>{tp ? <span className={`bdg ${tp.cls}`}>{tp.label}</span> : '—'}</td>
        {stCell}
        <td><span className="mono small">{item.runner || '—'}</span></td>
        {userCell}
        {timeCell}
      </>
    )
  }
  if (dimension === 'test') {
    return (
      <>
        {entityCell}
        {projCell}
        {stCell}
        <td>
          <span
            className="mono small"
            style={{ color: item.cases_passed ? 'var(--green-tx)' : 'var(--faint)' }}
          >
            {item.cases_passed || '—'}
          </span>
        </td>
        {userCell}
        {timeCell}
      </>
    )
  }
  // release:部署 URL/端口列(URL 为静态文本,点击行进任务工作台;不跳外网)
  const url = item.deploy_host ? `http://${item.deploy_host}${item.deploy_port ? `:${item.deploy_port}` : ''}` : null
  return (
    <>
      {entityCell}
      {projCell}
      {stCell}
      <td><span className="mono small" style={{ whiteSpace: 'nowrap' }}>{url || '—'}</span></td>
      <td><span className="mono small">{item.deploy_port ?? '—'}</span></td>
      {userCell}
      {timeCell}
    </>
  )
}

// ---- 快速创建对话框(照抄 vp openQuick 结构;关联字段=项目 + 需求) ----

interface QuickCreateDialogProps {
  open: boolean
  dimension: DimensionPageProps['dimension']
  createLabel: string
  onClose: () => void
}

function QuickCreateDialog({ open, dimension, onClose }: QuickCreateDialogProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [pid, setPid] = useState('')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [reqId, setReqId] = useState('')
  const [deployPort, setDeployPort] = useState('')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const { data: projData } = useProjectList({ status: 'active', page: 1, page_size: 100 })
  const projects = projData?.items ?? []
  // 项目默认选中:列表首个(vp openQuick 的 QC.pid 兜底一致)
  const activePid = pid || projects[0]?.project_id || ''

  // 该项目需求列表(项目口径,非"我创建的";服务端仍兜底校验)
  const { data: reqsData } = useQuery({
    queryKey: ['quick-create-reqs', activePid],
    queryFn: () => requirementsApi.list(activePid, { page: 1, page_size: 100 }),
    enabled: open && !!activePid && dimension !== 'requirements',
  })
  const reqs = reqsData?.data?.items ?? []
  // 需求下拉可选状态:dev=approved;test=approved/in_progress/done;release=approved/done
  // (与 vp 偏差留痕:不逐需求查任务态置灰,前置校验交服务端,避免 N+1)
  const selectableReqs = reqs.filter(r =>
    dimension === 'dev' ? r.status === 'approved' :
    dimension === 'test' ? ['approved', 'in_progress', 'done'].includes(r.status) :
    ['approved', 'done'].includes(r.status)
  )

  const close = () => {
    setTitle(''); setDescription(''); setReqId(''); setDeployPort(''); setErrorMsg(null)
    onClose()
  }

  const mutation = useMutation({
    mutationFn: async () => {
      if (dimension === 'requirements') {
        const d = await requirementsApi.create(activePid, {
          title: title.trim(),
          description: description.trim(),
        }).then(r => r.data)
        return { kind: 'requirement' as const, id: d.req_id }
      }
      const req = selectableReqs.find(r => r.req_id === reqId)
      const payload: CreateTaskPayload = {
        type: dimension,
        title: (title.trim() || `${req?.title || '任务'}`).slice(0, 200),
        description: description.trim(),
      }
      if (dimension === 'release') {
        payload.deploy_port = Number(deployPort)
      }
      const d = await createTask(reqId, payload)
      return { kind: 'task' as const, id: d.task_id }
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['dimension'] })
      close()
      // 创建成功跳详情页(vp quickSubmit 跳转一致)
      if (res.kind === 'requirement') {
        navigate(`/requirements/${res.id}`)
      } else {
        navigate(`/tasks/${res.id}`)
      }
    },
    onError: (err: Error) => {
      setErrorMsg(err?.message || '创建失败')
    },
  })

  const canSubmit =
    !!activePid &&
    !mutation.isPending &&
    (dimension === 'requirements'
      ? !!title.trim()
      : !!reqId && (dimension !== 'release' || /^(100\d{2})$/.test(deployPort)))

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) close() }}>
      <DialogContent onClose={close} className="w-[440px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Plus size={16} /> {QUICK_DIALOG_NAME[dimension]} · 快速创建</DialogTitle>
        </DialogHeader>

        {errorMsg && <Alert variant="error" onClose={() => setErrorMsg(null)}>{errorMsg}</Alert>}

        <div className="flex flex-col gap-4 py-2">
          <div className="field">
            <label>项目</label>
            <select
              className="input"
              value={activePid}
              onChange={(e) => { setPid(e.target.value); setReqId('') }}
            >
              {projects.map(p => (
                <option key={p.project_id} value={p.project_id}>{p.name}</option>
              ))}
            </select>
          </div>

          {dimension === 'requirements' ? (
            <>
              <div className="field">
                <label>标题</label>
                <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="需求标题" />
              </div>
              <div className="field">
                <label>描述(初始草稿,后续 AI 打磨)</label>
                <textarea className="input" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
              </div>
              <div className="hint">
                <GitBranch size={12} style={{ display: 'inline', verticalAlign: '-1px' }} />
                {' '}创建后平台 bot 自动从默认分支切出需求分支(所有绑定仓库)
              </div>
            </>
          ) : (
            <>
              <div className="field">
                <label>需求</label>
                <select className="input" value={reqId} onChange={(e) => setReqId(e.target.value)}>
                  <option value="">请选择需求</option>
                  {selectableReqs.map(r => (
                    <option key={r.req_id} value={r.req_id}>
                      {r.req_id.slice(0, 8)} · {r.title}
                    </option>
                  ))}
                </select>
                <div className="hint">前置不满足的需求未列出;服务端仍会兜底校验(需求状态/token/端口唯一性)</div>
              </div>
              {dimension === 'dev' && (
                <>
                  <div className="field">
                    <label>任务标题(留空默认取需求标题)</label>
                    <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
                  </div>
                  <div className="field">
                    <label>要让 AI 做什么(描述)</label>
                    <textarea className="input" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
                  </div>
                </>
              )}
              {dimension === 'test' && (
                <div className="hint">
                  <FlaskConical size={12} style={{ display: 'inline', verticalAlign: '-1px' }} />
                  {' '}AI 基于 PRD 验收标准 + 测试仓库存量用例生成用例,人审后执行
                </div>
              )}
              {dimension === 'release' && (
                <div className="field">
                  <label>部署端口(10000-10099,全平台唯一)</label>
                  <input className="input" type="number" value={deployPort} onChange={(e) => setDeployPort(e.target.value)} placeholder="10042" />
                </div>
              )}
            </>
          )}
        </div>

        <DialogFooter>
          <button className="btn" onClick={close}>取消</button>
          <button
            className="btn btn-pri"
            disabled={!canSubmit}
            onClick={() => { setErrorMsg(null); mutation.mutate() }}
          >
            {mutation.isPending ? '创建中…' : QUICK_DIALOG_NAME[dimension]}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// 辅助函数:根据状态返回颜色
function getStatusColor(status: string): string {
  const colorMap: Record<string, string> = {
    // 需求状态
    draft: 'zinc',
    polishing: 'blue',
    reviewing: 'amber',
    approved: 'green',
    in_progress: 'blue',
    done: 'green',
    archived: 'zinc',
    rejected: 'red',
    // 任务状态
    pending: 'zinc',
    running: 'blue',
    failed: 'red',
    cancelled: 'zinc',
    timeout: 'red',
    // 测试状态
    passed: 'green',
    cases_review: 'amber',
    // 发布状态
    deployed: 'green',
  }
  return colorMap[status] || 'zinc'
}

// 辅助函数:根据状态选项返回文本
function getStatusText(status: string, options: StatusOption[]): string {
  const opt = options.find(o => o.value === status)
  return opt?.label || status
}

// 辅助函数:格式化日期
function formatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateStr
  }
}
