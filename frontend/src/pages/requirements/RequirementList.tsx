/**
 * RequirementList — 需求列表页
 * 标题"需求" + 主按钮"新建需求" + 表格 + 分页 + 空态 + 创建对话框
 */

import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Plus, Eye, ClipboardList, ChevronDown, Check, X } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import { Avatar } from '@/components/ui/Avatar'
import { useProjectMembers } from '@/api/projects'
import type { ProjectMember } from '@/api/projects'
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

// R1:成员角色徽章映射(与 MemberManagement roleBadgeMap 同口径)
const roleBadgeMap: Record<string, { label: string; variant: 'primary' | 'secondary' | 'outline' }> = {
  owner: { label: '所有者', variant: 'primary' },
  editor: { label: '编辑者', variant: 'secondary' },
  viewer: { label: '观察者', variant: 'outline' },
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
    related_user_ids: [] as string[], // R1 关联用户(项目成员多选)
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
  const branchPreview = formData.title
    ? `req-${formData.title.toLowerCase().replace(/[^a-z0-9一-龥]+/g, '-').replace(/^-|-$/g, '')}`
    : 'req-'

  function handleCreate() {
    if (!projectId || !formData.title.trim() || !formData.description.trim()) {
      setFormError('标题和描述为必填项')
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
          related_user_ids: formData.related_user_ids, // R1:空数组照传,后端静默剔除非成员
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
            related_user_ids: [],
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

/**
 * RelatedUserSelect — R1 关联用户多选下拉
 * - 触发框:复用 .input 类,已选项以 .chip(头像+昵称+×)内嵌展示
 * - 下拉面板:对齐 ProjectDetail 操作菜单写法(bg-surface border-border shadow-lg z-10)
 * - 候选行:头像+昵称+角色徽章(对齐成员管理/邀请候选行样式),支持昵称/用户名搜索
 * - 全部现有 token,零新视觉
 */
function RelatedUserSelect({
  members,
  value,
  onChange,
}: {
  members: ProjectMember[]
  value: string[]
  onChange: (ids: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const wrapRef = useRef<HTMLDivElement>(null)

  // 点击面板外关闭
  useEffect(() => {
    if (!open) return
    function onDocMouseDown(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocMouseDown)
    return () => document.removeEventListener('mousedown', onDocMouseDown)
  }, [open])

  const toggle = (userId: string) => {
    onChange(
      value.includes(userId)
        ? value.filter((id) => id !== userId)
        : [...value, userId],
    )
  }

  // 搜索定位(昵称/用户名,不区分大小写)
  const keyword = search.trim().toLowerCase()
  const candidates = members.filter((m) =>
    !keyword ||
    (m.nickname || '').toLowerCase().includes(keyword) ||
    m.username.toLowerCase().includes(keyword),
  )
  const selectedMembers = value
    .map((id) => members.find((m) => m.user_id === id))
    .filter((m): m is ProjectMember => !!m)

  return (
    <div className="relative" ref={wrapRef}>
      {/* 触发框:已选 chips 内嵌在 .input 框内 */}
      <div
        className="input flex items-center flex-wrap gap-1.5 cursor-pointer min-h-[34px]"
        onClick={() => setOpen((o) => !o)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setOpen((o) => !o) }}
      >
        {selectedMembers.length === 0 ? (
          <span className="text-text-muted">选择关联用户(项目成员,可多选)</span>
        ) : (
          selectedMembers.map((m) => (
            <span key={m.user_id} className="chip" onClick={(e) => e.stopPropagation()}>
              <Avatar src={m.avatar_url} alt={m.nickname || m.username} size={16} />
              {m.nickname || m.username}
              <button
                type="button"
                className="hover:text-red-fg"
                aria-label={`移除 ${m.nickname || m.username}`}
                onClick={(e) => { e.stopPropagation(); toggle(m.user_id) }}
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))
        )}
        <ChevronDown className="w-4 h-4 text-text-muted ml-auto shrink-0" />
      </div>

      {/* 下拉面板:搜索 + 成员候选列表(头像+昵称+角色徽章+勾选态) */}
      {open && (
        <div className="absolute left-0 right-0 top-full mt-1 z-10 bg-surface border border-border rounded-md shadow-lg overflow-hidden">
          <div className="p-2 border-b border-border">
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索成员(昵称/用户名)"
              className="h-8 text-xs"
            />
          </div>
          <div className="max-h-60 overflow-y-auto py-1">
            {candidates.length === 0 ? (
              <div className="px-3 py-4 text-sm text-text-muted text-center">无匹配成员</div>
            ) : (
              candidates.map((m) => {
                const rb = roleBadgeMap[m.role] ?? roleBadgeMap.viewer
                const checked = value.includes(m.user_id)
                return (
                  <button
                    key={m.user_id}
                    type="button"
                    className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-surface-strong text-text text-left"
                    onClick={() => toggle(m.user_id)}
                  >
                    <Avatar src={m.avatar_url} alt={m.nickname || m.username} size={24} />
                    <span className="flex flex-col min-w-0 flex-1">
                      <span className="truncate">{m.nickname || m.username}</span>
                      {m.nickname && m.username !== m.nickname && (
                        <span className="text-xs text-text-muted truncate">@{m.username}</span>
                      )}
                    </span>
                    <Badge variant={rb.variant}>{rb.label}</Badge>
                    {checked && <Check className="w-4 h-4 text-primary shrink-0" />}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
