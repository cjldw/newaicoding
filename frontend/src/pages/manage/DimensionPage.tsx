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
  Plus, Shield, ChevronRight, GitBranch, Folder, FlaskConical, Trash2,
} from 'lucide-react'
import { useDimensionList, type DimensionItem } from '@/api/dashboard'
import { useProjectList, useProjectMembers } from '@/api/projects'
import { requirementsApi, useBranchPreview } from '@/api/requirements'
import type { RequirementPriority } from '@/api/requirements'
import { useDebounce } from '@/hooks/useDebounce'
import { createTask, type CreateTaskPayload } from '@/api/tasks'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/Dialog'
import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import { RelatedUserSelect } from '@/pages/requirements/RelatedUserSelect'

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

// ---- R1.F1:需求维完整创建表单约束(与 RequirementList 同口径) ----
// 原型链接:label ≤20 可空 / url http(s):// 开头 / 最多 10 条;行内红字文案照分片
const MAX_PROTOTYPE_LINKS = 10
const PROTOTYPE_URL_PATTERN = /^https?:\/\//i
// 表单行形态(label 空串;提交时非空才带,空行整行剔除)
interface PrototypeLinkDraft { label: string; url: string }

function isPrototypeLinkRowError(row: PrototypeLinkDraft): boolean {
  const url = row.url.trim()
  if (url !== '') return !PROTOTYPE_URL_PATTERN.test(url)
  return row.label.trim() !== '' // 有标签无 URL = 半填行,同样拦截
}

// 空表单(关弹重置用;useState 惰性初始化需工厂,引用类型字段不能共享同一对象)
function emptyRequirementForm() {
  return {
    title: '',
    background: '',
    description: '',
    acceptance_criteria: '',
    priority: 'medium' as RequirementPriority,
    req_branch: '',
    delivery_date: '', // input[type=date] 原生值 YYYY-MM-DD;空串=不设置
    related_user_ids: [] as string[], // 关联用户(项目成员多选)
    prototype_links: [] as PrototypeLinkDraft[], // 原型链接(标签可选 + URL 必填)
  }
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
        {/* R1.F1:requirements 维改为完整表单 dialog,按钮文案去掉"(快速创建)"后缀 */}
        {createLabel && (
          <div className="acts">
            <button className="btn btn-pri" onClick={() => setQuickOpen(true)}>
              <Plus className="w-4 h-4" />
              {dimension === 'requirements' ? createLabel : `${createLabel}(快速创建)`}
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

        {/* 脚注+分页合一条 foot-split:左权限说明,右分页 */}
        <div className="card-foot foot-split">
          <div className="flex items-center gap-1.5">
            <Shield size={13} />
            <span>归档 / 软删项目数据不出现;点击行进入详情</span>
          </div>
          {totalPages > 1 && (
            <div className="flex items-center gap-2">
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
        </div>
      </div>

      {/* R1.F1:requirements 维用完整表单 dialog(对齐项目详情页);其他三维仍走快速创建 */}
      {createLabel && (
        dimension === 'requirements' ? (
          <RequirementCreateDialog
            open={quickOpen}
            onClose={() => setQuickOpen(false)}
          />
        ) : (
          <QuickCreateDialog
            open={quickOpen}
            dimension={dimension}
            createLabel={createLabel}
            onClose={() => setQuickOpen(false)}
          />
        )
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
  const entityCell = (
    <td>
      {/* 标题列长文本省略(.tbl .cell-txt) */}
      <div className="cell-txt"><b>{item.key.slice(0, 8)}</b> · {item.title}</div>
    </td>
  )
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
        // 后端 title max_length=128,截断对齐(超长需求标题不再 422)
        title: (title.trim() || `${req?.title || '任务'}`).slice(0, 128),
        // R1.F3:test/release 无描述输入框,description 恒空;后端 min_length=1 必 422
        // 兜底为需求标题,dev 留空描述同样受益
        description: description.trim() || req?.title || '任务描述',
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
          <Button variant="ghost" onClick={close}>取消</Button>
          <Button
            variant="primary"
            disabled={!canSubmit}
            onClick={() => { setErrorMsg(null); mutation.mutate() }}
          >
            {mutation.isPending ? '创建中…' : QUICK_DIALOG_NAME[dimension]}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---- R1.F1:需求维完整创建对话框(表单结构照抄 RequirementList 创建 dialog) ----
// 与项目详情页差异:①保留项目选择器(manage 跨项目入口)②关联用户按 activePid 动态加载
// ③提交走 requirementsApi.create(activePid, payload),成功后跳需求详情页

interface RequirementCreateDialogProps {
  open: boolean
  onClose: () => void
}

function RequirementCreateDialog({ open, onClose }: RequirementCreateDialogProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [pid, setPid] = useState('')
  const [formData, setFormData] = useState(emptyRequirementForm)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const { data: projData } = useProjectList({ status: 'active', page: 1, page_size: 100 })
  const projects = projData?.items ?? []
  // 项目默认选中:列表首个(与 QuickCreateDialog 兜底一致)
  const activePid = pid || projects[0]?.project_id || ''

  // 关联用户候选 = 选中项目成员全量(≤50;切换项目即换候选)
  const { data: membersData } = useProjectMembers(activePid)
  const members = membersData?.items ?? []

  // 分支预览(R1.F2:改调后端接口取真实拼音,default_req_branch 权威生成;
  // 本地 map 成 □ 的旧预览已移除;标题停顿 300ms 才请求,失败静默显示占位)
  const debouncedTitle = useDebounce(formData.title.trim(), 300)
  const { data: branchData } = useBranchPreview(debouncedTitle)
  const branchPreview = branchData?.branch || ''

  // 原型链接行操作(追加/删除/编辑)
  function addPrototypeLink() {
    setFormData((f) => ({
      ...f,
      prototype_links: [...f.prototype_links, { label: '', url: '' }],
    }))
  }
  function removePrototypeLink(idx: number) {
    setFormData((f) => ({
      ...f,
      prototype_links: f.prototype_links.filter((_, i) => i !== idx),
    }))
  }
  function updatePrototypeLink(idx: number, patch: Partial<PrototypeLinkDraft>) {
    setFormData((f) => ({
      ...f,
      prototype_links: f.prototype_links.map((row, i) => (i === idx ? { ...row, ...patch } : row)),
    }))
  }

  const close = () => {
    setPid('')
    setFormData(emptyRequirementForm())
    setErrorMsg(null)
    onClose()
  }

  const mutation = useMutation({
    mutationFn: async () => {
      const d = await requirementsApi.create(activePid, {
        title: formData.title.trim(),
        background: formData.background.trim() || undefined,
        description: formData.description.trim(),
        acceptance_criteria: formData.acceptance_criteria.trim() || undefined,
        priority: formData.priority,
        req_branch: formData.req_branch.trim() || undefined,
        delivery_date: formData.delivery_date || undefined, // 可选不填
        related_user_ids: formData.related_user_ids, // 空数组照传,后端静默剔除非成员
        prototype_links: formData.prototype_links
          .filter((row) => row.label.trim() !== '' || row.url.trim() !== '') // 整行全空不提交
          .map((row) => ({
            label: row.label.trim() || null,
            url: row.url.trim(),
          })),
      }).then((r) => r.data)
      return d.req_id
    },
    onSuccess: (reqId: string) => {
      queryClient.invalidateQueries({ queryKey: ['dimension'] })
      close()
      // 创建成功跳详情页(与 QuickCreateDialog 跳转一致)
      navigate(`/requirements/${reqId}`)
    },
    onError: (err: Error) => {
      setErrorMsg(err?.message || '创建失败')
    },
  })

  function handleSubmit() {
    if (!activePid || !formData.title.trim() || !formData.description.trim()) {
      setErrorMsg('标题和描述为必填项')
      return
    }
    // URL 行内校验(空行剔除;非法/半填行红字提示并拦截提交,文案照分片)
    if (formData.prototype_links.some(isPrototypeLinkRowError)) {
      setErrorMsg('URL 需以 http(s):// 开头')
      return
    }
    setErrorMsg(null)
    mutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) close() }}>
      <DialogContent onClose={close}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Plus size={16} /> 新建需求</DialogTitle>
        </DialogHeader>

        {errorMsg && <Alert variant="error" onClose={() => setErrorMsg(null)}>{errorMsg}</Alert>}

        <div className="flex flex-col gap-4 py-2">
          {/* 项目选择器(manage 跨项目入口特有;切换即重置关联用户,防跨项目残留) */}
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              项目 <span className="text-red-fg">*</span>
            </label>
            <select
              className="input"
              value={activePid}
              onChange={(e) => {
                setPid(e.target.value)
                setFormData((f) => ({ ...f, related_user_ids: [] }))
              }}
            >
              {projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              标题 <span className="text-red-fg">*</span>
            </label>
            <Input
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="输入需求标题"
            />
            {formData.title && (
              <div className="mt-1 text-xs text-text-muted">
                分支预览: <code className="text-primary">{branchPreview || '生成中...'}</code>
                (以创建时系统生成为准;可手动改填覆盖)
              </div>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">背景</label>
            <Textarea
              value={formData.background}
              onChange={(e) => setFormData({ ...formData, background: e.target.value })}
              placeholder="需求背景(可选)"
              rows={2}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              描述 <span className="text-red-fg">*</span>
            </label>
            <Textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="详细描述需求内容"
              rows={3}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">验收标准</label>
            <Textarea
              value={formData.acceptance_criteria}
              onChange={(e) => setFormData({ ...formData, acceptance_criteria: e.target.value })}
              placeholder="验收标准(可选)"
              rows={2}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">优先级</label>
            <Select
              value={formData.priority}
              onChange={(e) => setFormData({ ...formData, priority: (e.target.value as RequirementPriority) })}
              options={[
                { label: '低', value: 'low' },
                { label: '中', value: 'medium' },
                { label: '高', value: 'high' },
              ]}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">需求分支</label>
            <Input
              value={formData.req_branch}
              onChange={(e) => setFormData({ ...formData, req_branch: e.target.value })}
              placeholder={branchPreview || 'feat/…'}
            />
            <div className="hint">
              <GitBranch size={12} style={{ display: 'inline', verticalAlign: '-1px' }} />
              {' '}留空则创建时平台自动从默认分支切出需求分支(所有绑定仓库)
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              交付时间 <span className="text-xs font-normal text-text-muted">(可选)</span>
            </label>
            <Input
              type="date"
              value={formData.delivery_date}
              onChange={(e) => setFormData({ ...formData, delivery_date: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              关联用户 <span className="text-xs font-normal text-text-muted">(可选)</span>
            </label>
            <RelatedUserSelect
              members={members}
              value={formData.related_user_ids}
              onChange={(ids) => setFormData({ ...formData, related_user_ids: ids })}
            />
          </div>
          {/* 原型链接行组(标签可选 ≤20 + URL 必填 http(s)://;≤10 条,超限禁加+提示) */}
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              原型链接 <span className="text-xs font-normal text-text-muted">(可选)</span>
            </label>
            <div className="space-y-2">
              {formData.prototype_links.map((row, idx) => {
                const rowError = isPrototypeLinkRowError(row)
                return (
                  <div key={idx} className="flex items-start gap-2">
                    <Input
                      value={row.label}
                      onChange={(e) => updatePrototypeLink(idx, { label: e.target.value })}
                      placeholder="链接标签(可选)"
                      maxLength={20}
                      className="w-40 shrink-0"
                      aria-label={`链接 ${idx + 1} 标签`}
                    />
                    <div className="flex-1 min-w-0">
                      <Input
                        value={row.url}
                        onChange={(e) => updatePrototypeLink(idx, { url: e.target.value })}
                        placeholder="URL"
                        className={rowError ? 'border-red-border' : undefined}
                        aria-label={`链接 ${idx + 1} URL`}
                      />
                      {rowError && (
                        <div className="mt-1 text-xs text-red-fg">URL 需以 http(s):// 开头</div>
                      )}
                    </div>
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost icon-btn shrink-0"
                      title="删除"
                      aria-label={`删除链接 ${idx + 1}`}
                      onClick={() => removePrototypeLink(idx)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                )
              })}
            </div>
            <div className="mt-2 flex items-center gap-2">
              <Button
                variant="default"
                size="sm"
                onClick={addPrototypeLink}
                disabled={formData.prototype_links.length >= MAX_PROTOTYPE_LINKS}
              >
                <Plus className="w-3.5 h-3.5 mr-1" />
                添加链接
              </Button>
              {formData.prototype_links.length >= MAX_PROTOTYPE_LINKS && (
                <span className="text-xs text-text-muted">最多 10 条</span>
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={close}>取消</Button>
          <Button
            variant="primary"
            disabled={mutation.isPending}
            onClick={handleSubmit}
          >
            {mutation.isPending ? '创建中…' : '创建'}
          </Button>
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
