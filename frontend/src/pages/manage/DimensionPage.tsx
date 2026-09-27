/**
 * 四维管理通用页面组件
 * 支持 requirements/dev/test/release 四个维度
 * R22.F2(BUG-UI-069):统一 audit-logs/vp pageManage 范式——page-head(带快速创建按钮)
 * + card(fbar 筛选区 → scrollx>tbl 表格区 → card-foot 说明);各维列定义照抄 vp L1665-1680;
 * 收敛 BUG-UI-052/053/054/055/059/060/061/062
 * R1:任务三维创建入口统一——页头单一"新建任务"按钮 + TaskCreateDialog(表单 R2-R5 完善);
 * 原 QuickCreateDialog 及分类型按钮(新建开发/测试/发布任务)移除;requirements 维保留完整表单
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { LucideIcon } from 'lucide-react'
import {
  Plus, Pencil, Shield, ChevronRight, GitBranch, Folder, Trash2,
} from 'lucide-react'
import { useDimensionList, type DimensionItem } from '@/api/dashboard'
import { useProjectList, useProjectMembers } from '@/api/projects'
import {
  requirementsApi, useBranchPreview, useDeleteRequirement,
} from '@/api/requirements'
import type { RequirementPriority } from '@/api/requirements'
import { useDebounce } from '@/hooks/useDebounce'
import { useDeleteTask, useTaskDetail, useUpdateTask, type UpdateTaskPayload } from '@/api/tasks'
import { RequirementEditDialog } from '@/pages/requirements/RequirementEditDialog'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/Dialog'
import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import { RelatedUserSelect } from '@/pages/requirements/RelatedUserSelect'
import { TaskCreateDialog } from './TaskCreateDialog'

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

// R4.F1:需求禁删状态集合 = 评审通过(approved)及之后的下游链路(已产生交付数据);
// 关联任务前端列表无此数据,删除按钮不因此禁用,后端 400 兜底
const REQ_NO_DELETE_STATUSES = ['approved', 'in_progress', 'done', 'archived']

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
  // R2.F1/R2.F2:行内编辑入口(requirements 全状态可编辑;任务维仅 pending,其余禁用兜底)
  const [editItem, setEditItem] = useState<DimensionItem | null>(null)
  // R4.F1/R4.F2:行内删除入口(确认弹窗;失败后端 message 用 Alert 展示)
  const [deleteItem, setDeleteItem] = useState<DimensionItem | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const pageSize = 20

  const { data, isLoading } = useDimensionList(dimension, {
    status: status || undefined,
    project_id: projectId || undefined,
    q: q || undefined,
    page,
    page_size: pageSize,
  })

  const deleteRequirementMutation = useDeleteRequirement()
  const deleteTaskMutation = useDeleteTask()
  const deleting = deleteRequirementMutation.isPending || deleteTaskMutation.isPending

  const closeDelete = () => {
    setDeleteItem(null)
    setDeleteError(null)
  }

  const handleDelete = () => {
    if (!deleteItem) return
    setDeleteError(null)
    const onError = (err: Error) => setDeleteError(err?.message || '删除失败')
    if (dimension === 'requirements') {
      deleteRequirementMutation.mutate(
        { reqId: deleteItem.key },
        { onSuccess: closeDelete, onError },
      )
    } else {
      deleteTaskMutation.mutate(
        { taskId: deleteItem.key },
        { onSuccess: closeDelete, onError },
      )
    }
  }

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
        {/* R1:文案由 ManagePages 传入——任务管理页为"新建任务"(统一入口),需求页为"新建需求";
            test/release 维不再传 createLabel,分类型按钮(新建测试任务/新建发布任务)随之移除 */}
        {createLabel && (
          <div className="acts">
            <button className="btn btn-pri" onClick={() => setQuickOpen(true)}>
              <Plus className="w-4 h-4" />
              {createLabel}
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
                    <td>
                      <div className="flex items-center gap-1">
                        {/* R2.F1/R2.F2:「编辑」按钮(stopPropagation 防触发行跳转;权限恒显,后端 403 兜底) */}
                        <button
                          className="btn btn-sm"
                          disabled={dimension !== 'requirements' && item.status !== 'pending'}
                          title={
                            dimension !== 'requirements' && item.status !== 'pending'
                              ? '任务已开始,不可编辑'
                              : '编辑'
                          }
                          onClick={(e) => { e.stopPropagation(); setEditItem(item) }}
                        >
                          编辑
                        </button>
                        {/* R4.F1/R4.F2:「删除」按钮(danger 态;需求维按禁删状态集合禁用,
                            任务三维仅 pending 可删;关联任务前端不可知,后端 400 兜底) */}
                        {(() => {
                          const reqLocked = dimension === 'requirements'
                            && REQ_NO_DELETE_STATUSES.includes(item.status)
                          const taskLocked = dimension !== 'requirements' && item.status !== 'pending'
                          return (
                            <button
                              className="btn btn-sm btn-danger"
                              disabled={reqLocked || taskLocked}
                              title={
                                reqLocked
                                  ? '评审通过的需求不可删除'
                                  : taskLocked
                                    ? '任务已开始,不可删除'
                                    : '删除'
                              }
                              onClick={(e) => { e.stopPropagation(); setDeleteError(null); setDeleteItem(item) }}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )
                        })()}
                        <ChevronRight size={14} />
                      </div>
                    </td>
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

      {/* R1:requirements 维用完整表单 dialog(对齐项目详情页);任务三维改用统一 TaskCreateDialog
          (表单结构 R2-R5 完善;原 QuickCreateDialog 已随分类型按钮一并移除) */}
      {createLabel && (
        dimension === 'requirements' ? (
          <RequirementCreateDialog
            open={quickOpen}
            onClose={() => setQuickOpen(false)}
          />
        ) : (
          <TaskCreateDialog
            open={quickOpen}
            onClose={() => setQuickOpen(false)}
          />
        )
      )}

      {/* R2.F1/R2.F2:行内编辑弹窗(requirements / 任务三维共用同一入口)
          R5.F1:需求编辑弹窗抽为共享组件(与项目详情页 RequirementList 共用) */}
      {editItem && dimension === 'requirements' && (
        <RequirementEditDialog
          reqId={editItem.key}
          projectId={editItem.project.project_id}
          onClose={() => setEditItem(null)}
        />
      )}
      {editItem && dimension !== 'requirements' && (
        <TaskEditDialog item={editItem} onClose={() => setEditItem(null)} />
      )}

      {/* R4.F1/R4.F2:删除确认弹窗(照 ModelConfigManagement 删除确认惯例:
          标题 + 含名称正文 + 危险操作提示;失败 Alert 展示后端 message) */}
      <Dialog open={!!deleteItem} onOpenChange={(o) => { if (!o) closeDelete() }}>
        <DialogContent onClose={closeDelete}>
          <DialogHeader>
            <DialogTitle>删除{dimension === 'requirements' ? '需求' : '任务'}</DialogTitle>
            <DialogDescription>
              确定删除{dimension === 'requirements' ? '需求' : `${TYPE_BADGE[deleteItem?.type || '']?.label || '任务'}任务`}
              「{deleteItem?.title}」吗?该操作不可恢复。
            </DialogDescription>
          </DialogHeader>
          {deleteError && <Alert variant="error" onClose={() => setDeleteError(null)}>{deleteError}</Alert>}
          <DialogFooter>
            <Button variant="ghost" onClick={closeDelete}>取消</Button>
            <Button variant="danger" disabled={deleting} onClick={handleDelete}>
              {deleting ? '删除中…' : '确定'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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
  // 项目默认选中:列表首个
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
      // 创建成功跳详情页
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

// ---- R2.F2:任务三维编辑对话框(按 type 出字段;不含需求选择/类型/状态) ----
// 入口已挡非 pending 行(按钮禁用);后端状态守卫 400 兜底

interface TaskEditDialogProps {
  item: DimensionItem
  onClose: () => void
}

function TaskEditDialog({ item, onClose }: TaskEditDialogProps) {
  const [form, setForm] = useState({
    title: '', description: '', base_branch: '', work_branch: '',
    deploy_host: '', deploy_port: '', deploy_script: '',
  })
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [filledTaskId, setFilledTaskId] = useState('')

  // 详情到达即回填(仅一次;详情 5s 轮询不覆盖编辑中表单)
  const { data: detail } = useTaskDetail(item.key)
  useEffect(() => {
    if (detail && detail.task_id !== filledTaskId) {
      setFilledTaskId(detail.task_id)
      setForm({
        title: detail.title,
        description: detail.description || '',
        base_branch: detail.base_branch || '',
        work_branch: detail.work_branch || '',
        deploy_host: detail.deploy_host || '',
        deploy_port: detail.deploy_port != null ? String(detail.deploy_port) : '',
        deploy_script: detail.deploy_script || '',
      })
    }
  }, [detail, filledTaskId])

  const updateMutation = useUpdateTask()
  const taskType = detail?.type || item.type || ''
  const typeLabel = TYPE_BADGE[taskType]?.label || '任务'

  const close = () => {
    setFilledTaskId('')
    setErrorMsg(null)
    onClose()
  }

  function handleSubmit() {
    if (!form.title.trim()) {
      setErrorMsg('标题为必填项')
      return
    }
    const payload: UpdateTaskPayload = {
      title: form.title.trim(),
      description: form.description.trim(),
    }
    if (taskType === 'dev') {
      payload.base_branch = form.base_branch.trim()
      payload.work_branch = form.work_branch.trim()
    }
    if (taskType === 'release') {
      if (!/^(100\d{2})$/.test(form.deploy_port)) {
        setErrorMsg('部署端口需为 10000-10099')
        return
      }
      payload.deploy_host = form.deploy_host.trim()
      payload.deploy_port = Number(form.deploy_port)
      payload.deploy_script = form.deploy_script
    }
    setErrorMsg(null)
    updateMutation.mutate(
      { taskId: item.key, payload },
      {
        // useUpdateTask 已失效 task 详情 + 四维列表缓存
        onSuccess: close,
        onError: (err: Error) => setErrorMsg(err?.message || '保存失败'),
      },
    )
  }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) close() }}>
      <DialogContent onClose={close} className="w-[440px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Pencil size={16} /> 编辑{typeLabel}任务</DialogTitle>
        </DialogHeader>

        {errorMsg && <Alert variant="error" onClose={() => setErrorMsg(null)}>{errorMsg}</Alert>}
        {!detail && <div className="hint">加载任务详情...</div>}

        <div className="flex flex-col gap-4 py-2">
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              标题 <span className="text-red-fg">*</span>
            </label>
            <Input
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              maxLength={128}
              placeholder="任务标题"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">描述</label>
            <Textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="本次要做什么(可选)"
              rows={3}
              maxLength={2000}
            />
          </div>
          {/* dev 维:分支两项;test 维:仅标题/描述 */}
          {taskType === 'dev' && (
            <>
              <div className="flex flex-col gap-1.5">
                <label className="block text-sm font-medium text-text">基础分支(base_branch)</label>
                <Input
                  value={form.base_branch}
                  onChange={(e) => setForm({ ...form, base_branch: e.target.value })}
                  maxLength={64}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="block text-sm font-medium text-text">工作分支(work_branch)</label>
                <Input
                  value={form.work_branch}
                  onChange={(e) => setForm({ ...form, work_branch: e.target.value })}
                  maxLength={64}
                />
              </div>
            </>
          )}
          {/* release 维:部署三项(端口冲突由后端 7001 校验,错误行内展示) */}
          {taskType === 'release' && (
            <>
              <div className="flex flex-col gap-1.5">
                <label className="block text-sm font-medium text-text">部署主机(deploy_host)</label>
                <Input
                  value={form.deploy_host}
                  onChange={(e) => setForm({ ...form, deploy_host: e.target.value })}
                  maxLength={253}
                  placeholder="不含协议与路径"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="block text-sm font-medium text-text">部署端口(deploy_port,10000-10099 全平台唯一)</label>
                <Input
                  type="number"
                  value={form.deploy_port}
                  onChange={(e) => setForm({ ...form, deploy_port: e.target.value })}
                  placeholder="10042"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="block text-sm font-medium text-text">部署脚本(deploy_script)</label>
                <Textarea
                  value={form.deploy_script}
                  onChange={(e) => setForm({ ...form, deploy_script: e.target.value })}
                  rows={3}
                />
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={close}>取消</Button>
          <Button
            variant="primary"
            disabled={updateMutation.isPending || !detail}
            onClick={handleSubmit}
          >
            {updateMutation.isPending ? '保存中…' : '保存'}
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
