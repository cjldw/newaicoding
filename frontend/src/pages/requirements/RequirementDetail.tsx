/**
 * RequirementDetail — 需求详情页
 * 页头(标题+状态徽章+优先级徽章+状态按钮)+ 基本信息卡片 + 关联任务列表
 */

import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Play, Send, CheckCircle, XCircle, FileText, ExternalLink, Pencil } from 'lucide-react'
import { TaskCreateDialog } from '@/pages/tasks/TaskCreateDialog'
import { BreadcrumbOverrideProvider } from '@/components/layout/Breadcrumb'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Textarea } from '@/components/ui/Textarea'
import { Avatar } from '@/components/ui/Avatar'
import { useProjectMembers } from '@/api/projects'
import { useAuthStore } from '@/stores/authStore'
import { RelatedUserSelect } from '@/pages/requirements/RelatedUserSelect'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import {
  useRequirementDetail, usePolishRequirement, useSubmitReview,
  useReviewRequirement, useCancelRequirement, useUpdateRequirement,
  getRequirementErrorMessage,
} from '@/api/requirements'
import type { RequirementStatus, RequirementPriority, RequirementTask } from '@/api/requirements'
// Markdown 简易渲染:共享实现(原本地版已并入 utils/markdown.ts,口径以更安全的 TaskDetail 版为准,
// 排版由 globals.css `.md` 作用域类承接,见容器上的 md 类)
import { renderMarkdown } from '@/utils/markdown'

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

// 任务类型徽章映射
const taskTypeMap: Record<string, { label: string; variant: 'secondary' | 'primary' | 'success' }> = {
  requirement: { label: '需求', variant: 'secondary' },
  dev: { label: '开发', variant: 'primary' },
  test: { label: '测试', variant: 'primary' },
  release: { label: '发布', variant: 'success' },
}

export function RequirementDetail() {
  const { reqId } = useParams<{ reqId: string }>()
  const navigate = useNavigate()
  const { data: requirement, isLoading } = useRequirementDetail(reqId ?? '')
  const polishRequirement = usePolishRequirement()
  const submitReview = useSubmitReview()
  const reviewRequirement = useReviewRequirement()
  const cancelRequirement = useCancelRequirement()
  // R2:关联用户编辑保存(现有零调用方 hook,R4 契约留痕后此处接通)
  const updateRequirement = useUpdateRequirement()
  const { user } = useAuthStore()
  // R2:项目成员(详情响应带 project_id)——关联用户 chips 昵称/头像解析 + 编辑权限判定 + 编辑候选
  // (members/memberMap 须在早退 return 之前算好:useMemo 等 hook 不可条件调用,同 breadcrumbCrumbs 先例)
  const { data: membersData } = useProjectMembers(requirement?.project_id ?? '')
  const members = membersData?.items ?? []
  const memberMap = useMemo(() => new Map(members.map((m) => [m.user_id, m])), [members])

  const [rejectDialog, setRejectDialog] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [releaseDialog, setReleaseDialog] = useState(false)
  const [cancelDialog, setCancelDialog] = useState(false)
  const [cancelReason, setCancelReason] = useState('')
  const [error, setError] = useState('')
  // R2:关联用户编辑态(草稿名单 + 对话框开关 + 对话框内错误)
  const [relatedUsersDialog, setRelatedUsersDialog] = useState(false)
  const [relatedUsersDraft, setRelatedUsersDraft] = useState<string[]>([])
  const [relatedUsersError, setRelatedUsersError] = useState('')

  // BUG-UI-063: 面包屑链 = 项目管理 / 需求 / {标题}
  const breadcrumbCrumbs = useMemo(() => [
    { label: '项目管理', href: '/projects' },
    { label: '需求' },
    { label: requirement?.title ?? '需求详情' },
  ], [requirement?.title])

  if (isLoading) {
    return <div className="page wide"><div className="page-loading">加载中...</div></div>
  }
  if (!requirement) {
    return <div className="page wide"><div className="page-loading">需求不存在</div></div>
  }

  const st = statusMap[requirement.status]
  const pr = priorityMap[requirement.priority]

  // R2:关联用户展示/编辑所需派生值(hook 已全部在早退 return 前调用,此处仅纯计算)
  const relatedUsers = requirement.related_user_ids ?? []
  // 编辑权限沿用需求编辑口径 = 项目 owner/editor(与 PATCH 后端 require_project_role editor 同口径;viewer 只读无入口)
  const myRole = user ? members.find((m) => m.user_id === user.user_id)?.role : undefined
  const canEdit = myRole === 'owner' || myRole === 'editor'

  // R2:打开编辑态(草稿 = 详情当前名单;已移出项目的成员不在候选中,后端保存时静默剔除)
  function openRelatedUsersDialog() {
    setRelatedUsersDraft(requirement?.related_user_ids ?? [])
    setRelatedUsersError('')
    setRelatedUsersDialog(true)
  }

  function handleSaveRelatedUsers() {
    // PATCH 字段面(Update schema 实测口径):
    // - related_user_ids 传即全量覆盖([] = 清空合法;非成员 id 后端静默剔除)→ 恒传
    // - delivery_date 是 PATCH 唯一「缺省即置 NULL」字段(R5 留痕)→ 必须回填当前值防误清
    // - title/background/description/acceptance_criteria/prototype_links 缺省 = 不动;
    //   且回填 title/description 会触发「评审中不可编辑」400(api :124 守卫)→ 一律不传
    if (!reqId) return
    updateRequirement.mutate(
      {
        reqId,
        data: {
          related_user_ids: relatedUsersDraft,
          delivery_date: requirement?.delivery_date ?? null,
        },
      },
      {
        onSuccess: () => {
          setRelatedUsersDialog(false)
          setError('')
        },
        onError: (err) => setRelatedUsersError(getRequirementErrorMessage(err)),
      },
    )
  }

  function handlePolish() {
    if (!reqId) return
    polishRequirement.mutate(reqId, {
      onSuccess: (data) => {
        navigate(`/tasks/${data.task_id}`)
      },
      onError: (err) => {
        setError(getRequirementErrorMessage(err))
      },
    })
  }

  function handleSubmitReview() {
    if (!reqId) return
    submitReview.mutate(reqId, {
      onSuccess: () => {
        setError('')
      },
      onError: (err) => {
        setError(getRequirementErrorMessage(err))
      },
    })
  }

  function handleApprove() {
    if (!reqId) return
    reviewRequirement.mutate({ reqId, data: { approved: true } }, {
      onSuccess: () => {
        setError('')
      },
      onError: (err) => {
        setError(getRequirementErrorMessage(err))
      },
    })
  }

  function handleReject() {
    if (!reqId || !rejectReason.trim()) return
    reviewRequirement.mutate({ reqId, data: { approved: false, reject_reason: rejectReason.trim() } }, {
      onSuccess: () => {
        setRejectDialog(false)
        setRejectReason('')
        setError('')
      },
      onError: (err) => {
        setError(getRequirementErrorMessage(err))
      },
    })
  }

  function handleCancel() {
    if (!reqId || !cancelReason.trim()) return
    cancelRequirement.mutate({ reqId, data: { reason: cancelReason.trim() } }, {
      onSuccess: () => {
        setCancelDialog(false)
        setCancelReason('')
        setError('')
      },
      onError: (err) => {
        setError(getRequirementErrorMessage(err))
      },
    })
  }

  // 判断是否可以创建测试/发布任务
  const hasDevTaskDone = requirement.tasks.some(t => t.type === 'dev' && t.status === 'done')
  const hasTestTaskPassed = requirement.tasks.some(t => t.type === 'test' && t.status === 'passed')

  return (
    <BreadcrumbOverrideProvider crumbs={breadcrumbCrumbs}>
    <div className="page wide">
      {/* 返回按钮 */}
      <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-4">
        <ArrowLeft className="w-4 h-4 mr-2" />
        返回
      </Button>

      {/* 页头 */}
      <div className="page-head">
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            {/* R2.F8(BUG-UI-068):h1 补 icon 惯例 */}
            <h1 className="flex items-center gap-2 text-2xl font-semibold text-text"><FileText size={18} /> {requirement.title}</h1>
            <Badge variant={st.variant}>{st.label}</Badge>
            <Badge variant={pr.variant}>{pr.label}</Badge>
          </div>
          <div className="text-sm text-text-muted">
            创建人: {requirement.created_by.nickname || requirement.created_by.username}
            <span className="mx-2">·</span>
            {new Date(requirement.created_at).toLocaleDateString('zh-CN')}
          </div>
        </div>
        <div className="flex gap-2">
          {requirement.status === 'draft' && (
            <Button variant="primary" onClick={handlePolish} disabled={polishRequirement.isPending}>
              <Play className="w-4 h-4 mr-2" />
              开始打磨
            </Button>
          )}
          {requirement.status === 'polishing' && (
            <Button variant="primary" onClick={handleSubmitReview} disabled={submitReview.isPending}>
              <Send className="w-4 h-4 mr-2" />
              提交评审
            </Button>
          )}
          {requirement.status === 'reviewing' && (
            <>
              <Button variant="primary" className="bg-success hover:bg-success/90" onClick={handleApprove} disabled={reviewRequirement.isPending}>
                <CheckCircle className="w-4 h-4 mr-2" />
                评审通过
              </Button>
              <Button variant="danger" onClick={() => setRejectDialog(true)}>
                <XCircle className="w-4 h-4 mr-2" />
                驳回
              </Button>
            </>
          )}
          {requirement.status === 'approved' && (
            <Button variant="primary" onClick={() => navigate('/tasks/create?type=dev')}>
              <FileText className="w-4 h-4 mr-2" />
              创建开发任务
            </Button>
          )}
          {requirement.status === 'in_progress' && hasDevTaskDone && (
            <Button variant="primary" onClick={() => navigate('/tasks/create?type=test')}>
              <FileText className="w-4 h-4 mr-2" />
              创建测试任务
            </Button>
          )}
          {requirement.status === 'in_progress' && hasTestTaskPassed && (
            <Button variant="primary" onClick={() => setReleaseDialog(true)}>
              <FileText className="w-4 h-4 mr-2" />
              创建发布任务
            </Button>
          )}
          {(requirement.status === 'draft' || requirement.status === 'polishing') && (
            <Button variant="ghost" onClick={() => setCancelDialog(true)}>
              取消需求
            </Button>
          )}
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mb-4 p-3 bg-red-bg border border-red-border rounded-md text-sm text-red-fg">
          {error}
        </div>
      )}

      {/* 基本信息卡片 */}
      <div className="bg-surface border border-border rounded-lg p-6 mb-6">
        <h2 className="text-lg font-semibold text-text mb-4">基本信息</h2>
        <div className="space-y-4">
          {requirement.background && (
            <div>
              <label className="block text-sm font-medium text-text-muted mb-1">背景</label>
              <div className="text-text prose prose-sm max-w-none md" dangerouslySetInnerHTML={{ __html: renderMarkdown(requirement.background) }} />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-text-muted mb-1">描述</label>
            <div className="text-text prose prose-sm max-w-none md" dangerouslySetInnerHTML={{ __html: renderMarkdown(requirement.description) }} />
          </div>
          {requirement.acceptance_criteria && (
            <div>
              <label className="block text-sm font-medium text-text-muted mb-1">验收标准</label>
              <div className="text-text prose prose-sm max-w-none md" dangerouslySetInnerHTML={{ __html: renderMarkdown(requirement.acceptance_criteria) }} />
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-text-muted mb-1">需求分支</label>
              <div className="text-text font-mono text-sm">{requirement.req_branch || '—'}</div>
            </div>
            <div>
              <label className="block text-sm font-medium text-text-muted mb-1">PRD 路径</label>
              <div className="text-text font-mono text-sm">{requirement.prd_file_path || '—'}</div>
            </div>
          </div>
          {/* R5:交付时间(有值才渲染,空清空合法;DATE 纯日期串直显) */}
          {requirement.delivery_date && (
            <div>
              <label className="block text-sm font-medium text-text-muted mb-1">交付时间</label>
              <div className="text-text">{requirement.delivery_date}</div>
            </div>
          )}
          {/* R2:关联用户(恒渲染行:空名单「未关联」;有值 头像+昵称 chips(复用 .chip-row/.chip,同 R4 链接行体系);
              已移出项目的历史关联 id 无成员信息,chip 回退「已移出成员」;owner/editor 行内编辑入口,viewer 无) */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-sm font-medium text-text-muted">关联用户</label>
              {canEdit && (
                <button
                  type="button"
                  className="btn btn-sm btn-ghost icon-btn"
                  title="编辑关联用户"
                  aria-label="编辑关联用户"
                  onClick={openRelatedUsersDialog}
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            {relatedUsers.length === 0 ? (
              <div className="text-sm text-text-muted">未关联</div>
            ) : (
              <div className="chip-row">
                {relatedUsers.map((uid) => {
                  const m = memberMap.get(uid)
                  return (
                    <span key={uid} className="chip" title={m?.username}>
                      <Avatar src={m?.avatar_url ?? null} alt={m?.nickname || m?.username || uid} size={16} />
                      {m?.nickname || m?.username || '已移出成员'}
                    </span>
                  )
                })}
              </div>
            )}
          </div>
          {/* R4:原型链接 chips(新开标签页 rel=noopener;label 空则「链接 N」;空列表不渲染该行) */}
          {!!requirement.prototype_links?.length && (
            <div>
              <label className="block text-sm font-medium text-text-muted mb-1">原型链接</label>
              <div className="chip-row">
                {requirement.prototype_links.map((link, idx) => (
                  <a
                    key={`${idx}-${link.url}`}
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="chip hover:bg-surface-strong"
                    title={link.url}
                  >
                    <ExternalLink className="w-3.5 h-3.5 ic" />
                    {link.label || `链接 ${idx + 1}`}
                  </a>
                ))}
              </div>
            </div>
          )}
          {(requirement.status === 'reviewing' || requirement.reviewed_by) && (
            <div className="border-t border-border pt-4">
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-text-muted mb-1">评审人</label>
                  <div className="text-text">
                    {requirement.reviewed_by?.nickname || requirement.reviewed_by?.username || '—'}
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-text-muted mb-1">评审时间</label>
                  <div className="text-text">
                    {requirement.reviewed_at ? new Date(requirement.reviewed_at).toLocaleDateString('zh-CN') : '—'}
                  </div>
                </div>
                {requirement.reject_reason && (
                  <div>
                    <label className="block text-sm font-medium text-text-muted mb-1">驳回理由</label>
                    <div className="text-red-fg">{requirement.reject_reason}</div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 关联任务列表(BUG-UI-078/079:标题区 p-6 内边距 + 表头灰底贯通,与 manage/releases 表格同风格) */}
      <div className="card mb-6">
        <div className="p-6 pb-0">
          <h2 className="text-lg font-semibold text-text mb-4">关联任务</h2>
        </div>
        {requirement.tasks.length === 0 ? (
          <div className="text-center py-8 text-text-muted">暂无关联任务</div>
        ) : (
          <div className="scrollx">
          <Table className="tbl">
            <TableHeader>
              <TableRow>
                <TableHead>任务类型</TableHead>
                <TableHead>标题</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>创建时间</TableHead>
                <TableHead className="ops">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {requirement.tasks.map((task: RequirementTask) => {
                const tt = taskTypeMap[task.type] || taskTypeMap.requirement
                return (
                  <TableRow key={task.task_id} className="rowclick" onClick={() => navigate(`/tasks/${task.task_id}`)}>
                    <TableCell>
                      <Badge variant={tt.variant}>{tt.label}</Badge>
                    </TableCell>
                    <TableCell className="font-medium text-text">{task.title}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{task.status}</Badge>
                    </TableCell>
                    <TableCell className="text-text-muted">—</TableCell>
                    <TableCell className="ops">
                      <button
                        className="btn btn-sm"
                        onClick={(e) => { e.stopPropagation(); navigate(`/tasks/${task.task_id}`) }}
                      >
                        查看
                      </button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
          </div>
        )}
      </div>

      {/* 驳回对话框 */}
      <Dialog open={rejectDialog} onOpenChange={setRejectDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>驳回需求</DialogTitle>
            <DialogDescription>
              请填写驳回理由,需求将返回打磨状态
            </DialogDescription>
          </DialogHeader>
          <div>
            <label className="block text-sm font-medium text-text mb-1.5">
              驳回理由 <span className="text-red-fg">*</span>
            </label>
            <Textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="请详细说明驳回原因"
              rows={4}
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRejectDialog(false)}>
              取消
            </Button>
            <Button variant="primary" onClick={handleReject} disabled={!rejectReason.trim()}>
              确认驳回
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 取消对话框 */}
      <Dialog open={cancelDialog} onOpenChange={setCancelDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>取消需求</DialogTitle>
            <DialogDescription>
              请填写取消理由,此操作不可恢复
            </DialogDescription>
          </DialogHeader>
          <div>
            <label className="block text-sm font-medium text-text mb-1.5">
              取消理由 <span className="text-red-fg">*</span>
            </label>
            <Textarea
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              placeholder="请说明取消原因"
              rows={4}
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setCancelDialog(false)}>
              取消
            </Button>
            <Button variant="danger" onClick={handleCancel} disabled={!cancelReason.trim()}>
              确认取消
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* R2:编辑关联用户对话框(复用 R1 RelatedUserSelect 多选;保存走 PATCH,
          useUpdateRequirement onSuccess 失效 ['requirement', reqId] → 详情自动刷新) */}
      <Dialog open={relatedUsersDialog} onOpenChange={setRelatedUsersDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>编辑关联用户</DialogTitle>
            <DialogDescription>
              选择与该需求相关的项目成员;空名单保存 = 清空关联
            </DialogDescription>
          </DialogHeader>
          <RelatedUserSelect
            members={members}
            value={relatedUsersDraft}
            onChange={setRelatedUsersDraft}
          />
          {relatedUsersError && (
            <div className="text-sm text-red-fg">{relatedUsersError}</div>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRelatedUsersDialog(false)}>
              取消
            </Button>
            <Button variant="primary" onClick={handleSaveRelatedUsers} disabled={updateRequirement.isPending}>
              {updateRequirement.isPending ? '保存中...' : '保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {releaseDialog && (
        <TaskCreateDialog
          reqId={reqId ?? ''}
          type="release"
          open={releaseDialog}
          onClose={() => setReleaseDialog(false)}
          onSuccess={(taskId) => { setReleaseDialog(false); navigate(`/tasks/${taskId}/deploy`) }}
        />
      )}
    </div>
    </BreadcrumbOverrideProvider>
  )
}
