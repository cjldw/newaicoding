/**
 * RequirementList — 需求列表页
 * 标题"需求" + 主按钮"新建需求" + 表格 + 分页 + 空态 + 创建对话框
 */

import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Plus, Eye, ClipboardList, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import { useProjectMembers } from '@/api/projects'
import { RelatedUserSelect } from '@/pages/requirements/RelatedUserSelect'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import {
  useRequirementList, useCreateRequirement, getRequirementErrorMessage,
} from '@/api/requirements'
import type { RequirementStatus, RequirementPriority } from '@/api/requirements'

// R4:原型链接约束(PRD:label ≤20 可空 / url http(s):// 开头 / 最多 10 条;行内红字文案照分片)
const MAX_PROTOTYPE_LINKS = 10
const PROTOTYPE_URL_PATTERN = /^https?:\/\//i
// 表单行形态(label 空串;提交时非空才带,空行整行剔除)
interface PrototypeLinkDraft { label: string; url: string }

function isPrototypeLinkRowError(row: PrototypeLinkDraft): boolean {
  const url = row.url.trim()
  if (url !== '') return !PROTOTYPE_URL_PATTERN.test(url)
  return row.label.trim() !== '' // 有标签无 URL = 半填行,同样拦截
}

// 状态徽章映射
const statusMap: Record<RequirementStatus, { label: string; variant: 'outline' | 'secondary' | 'primary' | 'success' | 'error' }> = {
  draft: { label: '草稿', variant: 'outline' },
  polishing: { label: '打磨中', variant: 'secondary' },
  reviewing: { label: '评审中', variant: 'primary' },
  approved: { label: '已通过', variant: 'success' },
  in_progress: { label: '进行中', variant: 'primary' },
  done: { label: '已完成', variant: 'success' },
  archived: { label: '已归档', variant: 'outline' },
  rejected: { label: '已取消', variant: 'error' },
}

// 优先级徽章映射
const priorityMap: Record<RequirementPriority, { label: string; variant: 'outline' | 'secondary' | 'primary' }> = {
  low: { label: '低', variant: 'outline' },
  medium: { label: '中', variant: 'secondary' },
  high: { label: '高', variant: 'primary' },
}

// R5:「今天」按 GMT+8(Asia/Shanghai)计算,与后端「UTC naive +8h」同约定;
// now + 8h 后取 UTC 年月日即为 GMT+8 墙钟日期,输出 YYYY-MM-DD 与 delivery_date(DATE 串)直接比较
function gmt8Today(): string {
  const gmt8 = new Date(Date.now() + 8 * 3600 * 1000)
  const y = gmt8.getUTCFullYear()
  const m = String(gmt8.getUTCMonth() + 1).padStart(2, '0')
  const d = String(gmt8.getUTCDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

// R5:逾期 = 已设交付时间 && delivery_date < 今天(GMT+8) && 非终态(done/archived 不标)
function isDeliveryOverdue(deliveryDate: string, status: RequirementStatus): boolean {
  if (['done', 'archived'].includes(status)) return false
  return deliveryDate < gmt8Today()
}

export function RequirementList() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const { data, isLoading } = useRequirementList(projectId ?? '', { page, page_size: 10 })
  const createRequirement = useCreateRequirement()

  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [formData, setFormData] = useState({
    title: '',
    background: '',
    description: '',
    acceptance_criteria: '',
    priority: 'medium' as RequirementPriority,
    req_branch: '',
    delivery_date: '', // R5 交付时间(input[type=date] 原生值 YYYY-MM-DD;空串=不设置)
    related_user_ids: [] as string[], // R1 关联用户(项目成员多选)
    prototype_links: [] as PrototypeLinkDraft[], // R4 原型链接(标签可选 + URL 必填)
  })
  const [formError, setFormError] = useState('')

  // R1:关联用户候选 = 项目成员全量(≤50,useProjectMembers)
  const { data: membersData } = useProjectMembers(projectId ?? '')
  const members = membersData?.items ?? []

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pageSize = 10
  const totalPages = Math.ceil(total / pageSize)

  // 实时生成分支预览
  // R34.F1:分支默认策略对齐后端 feat/{需求名首拼≤10}{日期}(后端权威生成;
  // 前端仅做预览——ASCII 取首字母,汉字逐字转□占位提示,实际首拼以后端为准;
  // 预览日期取本地墙钟,与后端 Asia/Shanghai 同日(跨日边界偏差可接受,仅预览)
  const branchPreview = (() => {
    const t = formData.title.trim()
    const slug = t
      ? Array.from(t.replace(/\s+/g, ''))
          .map((ch) => (/[a-z0-9]/i.test(ch) ? ch.toLowerCase() : /[一-龥]/.test(ch) ? '□' : ''))
          .join('')
          .slice(0, 10) || 'req'
      : '…'
    const now = new Date()
    const day = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`
    return `feat/${slug}${day}`
  })()

  // R4:原型链接行操作(追加/删除/编辑)
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

  function handleCreate() {
    if (!projectId || !formData.title.trim() || !formData.description.trim()) {
      setFormError('标题和描述为必填项')
      return
    }
    // R4:URL 行内校验(空行剔除;非法/半填行红字提示并拦截提交,文案照分片)
    if (formData.prototype_links.some(isPrototypeLinkRowError)) {
      setFormError('URL 需以 http(s):// 开头')
      return
    }
    createRequirement.mutate(
      {
        projectId,
        data: {
          title: formData.title.trim(),
          background: formData.background.trim() || undefined,
          description: formData.description.trim(),
          acceptance_criteria: formData.acceptance_criteria.trim() || undefined,
          priority: formData.priority,
          req_branch: formData.req_branch.trim() || undefined,
          delivery_date: formData.delivery_date || undefined, // R5:可选不填
          related_user_ids: formData.related_user_ids, // R1:空数组照传,后端静默剔除非成员
          prototype_links: formData.prototype_links
            .filter((row) => row.label.trim() !== '' || row.url.trim() !== '') // 整行全空不提交
            .map((row) => ({
              label: row.label.trim() || null,
              url: row.url.trim(),
            })),
        },
      },
      {
        onSuccess: () => {
          setShowCreateDialog(false)
          setFormData({
            title: '',
            background: '',
            description: '',
            acceptance_criteria: '',
            priority: 'medium',
            req_branch: '',
            delivery_date: '',
            related_user_ids: [],
            prototype_links: [],
          })
          setFormError('')
        },
        onError: (error) => {
          setFormError(getRequirementErrorMessage(error))
        },
      },
    )
  }

  return (
    <div>
      {/* 页头 */}
      <div className="page-head">
        {/* R2.F8(BUG-UI-068):h1 补 icon 惯例 */}
        <h1 className="flex items-center gap-2"><ClipboardList size={18} /> 需求</h1>
        {/* design.md 新增按钮规范:「新建」类主按钮统一放页头右上 acts 区(对齐 KnowledgeBase/DimensionPage) */}
        <div className="acts">
          <Button variant="primary" onClick={() => setShowCreateDialog(true)}>
            <Plus className="w-4 h-4 mr-1" />
            新建需求
          </Button>
        </div>
      </div>

      {/* 表格 */}
      {isLoading ? (
        <div className="text-center py-12 text-text-muted">加载中...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 text-text-muted">暂无需求 · 点击右上角「新建需求」创建</div>
      ) : (
        <>
          <div className="card">
          <div className="scrollx">
          <Table className="tbl">
            <TableHeader>
              <TableRow>
                <TableHead>标题</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>优先级</TableHead>
                <TableHead>创建人</TableHead>
                <TableHead>创建时间</TableHead>
                <TableHead>交付时间</TableHead>
                <TableHead className="ops w-[80px]">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => {
                const st = statusMap[item.status]
                const pr = priorityMap[item.priority]
                return (
                  <TableRow key={item.req_id}>
                    <TableCell className="font-medium text-text">
                      <span className="cell-txt">{item.title}</span>
                    </TableCell>
                    <TableCell>
                      <Badge variant={st.variant}>{st.label}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={pr.variant}>{pr.label}</Badge>
                    </TableCell>
                    <TableCell className="text-text-muted">
                      {item.created_by.nickname || item.created_by.username}
                    </TableCell>
                    <TableCell className="text-text-muted">
                      {new Date(item.created_at).toLocaleDateString('zh-CN')}
                    </TableCell>
                    {/* R5:交付时间(DATE 串直显)+ 逾期红徽章(非终态 && <GMT+8 今天;终态不标) */}
                    <TableCell className="text-text-muted">
                      {item.delivery_date ? (
                        <span className="inline-flex items-center gap-1.5">
                          {item.delivery_date}
                          {isDeliveryOverdue(item.delivery_date, item.status) && (
                            <span className="bdg b-red">已逾期</span>
                          )}
                        </span>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell className="ops">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => navigate(`/requirements/${item.req_id}`)}
                      >
                        <Eye className="w-4 h-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
          </div>

          {/* 分页:与表格同卡 foot-split(左统计右分页,替换原裸 tailwind mt-4 分页) */}
          <div className="card-foot foot-split">
            <span className="small faint">共 {total} 个需求</span>
            <div className="flex items-center gap-2">
              <span className="small">第 {page} / {totalPages} 页</span>
              <button
                className="btn btn-sm"
                disabled={page <= 1}
                onClick={() => setPage(p => p - 1)}
              >
                上一页
              </button>
              <button
                className="btn btn-sm"
                disabled={page >= totalPages}
                onClick={() => setPage(p => p + 1)}
              >
                下一页
              </button>
            </div>
          </div>
          </div>
        </>
      )}

      {/* 创建对话框 */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建需求</DialogTitle>
            <DialogDescription>
              创建一个新的需求,填写相关信息后提交
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-text mb-1.5">
                标题 <span className="text-red-fg">*</span>
              </label>
              <Input
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                placeholder="输入需求标题"
              />
              {formData.title && (
                <div className="mt-1 text-xs text-text-muted">
                  分支预览: <code className="text-primary">{branchPreview}</code>
                  (□ = 汉字首拼,以创建时系统生成为准;可手动改填覆盖)
                </div>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-text mb-1.5">背景</label>
              <Textarea
                value={formData.background}
                onChange={(e) => setFormData({ ...formData, background: e.target.value })}
                placeholder="需求背景(可选)"
                rows={2}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text mb-1.5">
                描述 <span className="text-red-fg">*</span>
              </label>
              <Textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="详细描述需求内容"
                rows={3}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text mb-1.5">验收标准</label>
              <Textarea
                value={formData.acceptance_criteria}
                onChange={(e) => setFormData({ ...formData, acceptance_criteria: e.target.value })}
                placeholder="验收标准(可选)"
                rows={2}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text mb-1.5">优先级</label>
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
            <div>
              <label className="block text-sm font-medium text-text mb-1.5">需求分支</label>
              <Input
                value={formData.req_branch}
                onChange={(e) => setFormData({ ...formData, req_branch: e.target.value })}
                placeholder={branchPreview}
              />
            </div>
            {/* R5:交付时间(可选;原生 input[type=date] 复用 .input 体系,到天) */}
            <div>
              <label className="block text-sm font-medium text-text mb-1.5">
                交付时间 <span className="text-xs font-normal text-text-muted">(可选)</span>
              </label>
              <Input
                type="date"
                value={formData.delivery_date}
                onChange={(e) => setFormData({ ...formData, delivery_date: e.target.value })}
              />
            </div>
            {/* R1:关联用户多选(项目成员,可搜索,chips 可移除) */}
            <div>
              <label className="block text-sm font-medium text-text mb-1.5">
                关联用户 <span className="text-xs font-normal text-text-muted">(可选)</span>
              </label>
              <RelatedUserSelect
                members={members}
                value={formData.related_user_ids}
                onChange={(ids) => setFormData({ ...formData, related_user_ids: ids })}
              />
            </div>
            {/* R4:原型链接行组(标签可选 ≤20 + URL 必填 http(s)://;≤10 条,超限禁加+提示) */}
            <div>
              <label className="block text-sm font-medium text-text mb-1.5">
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
            {formError && (
              <div className="text-sm text-red-fg">{formError}</div>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowCreateDialog(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              onClick={handleCreate}
              disabled={createRequirement.isPending}
            >
              {createRequirement.isPending ? '创建中...' : '创建'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
