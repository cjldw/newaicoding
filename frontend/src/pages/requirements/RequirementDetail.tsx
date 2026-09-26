/**
 * RequirementDetail — 需求详情页
 * 页头(标题+状态徽章+优先级徽章+状态按钮)+ 基本信息卡片 + 关联任务列表
 */

import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Play, Send, CheckCircle, XCircle, FileText, ExternalLink } from 'lucide-react'
import { TaskCreateDialog } from '@/pages/tasks/TaskCreateDialog'
import { BreadcrumbOverrideProvider } from '@/components/layout/Breadcrumb'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Textarea } from '@/components/ui/Textarea'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import {
  useRequirementDetail, usePolishRequirement, useSubmitReview,
  useReviewRequirement, useCancelRequirement, getRequirementErrorMessage,
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

  const [rejectDialog, setRejectDialog] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [releaseDialog, setReleaseDialog] = useState(false)
  const [cancelDialog, setCancelDialog] = useState(false)
  const [cancelReason, setCancelReason] = useState('')
  const [error, setError] = useState('')

  // BUG-UI-063: 面包屑链 = 项目管理 / 需求 / {标题}
  const breadcrumbCrumbs = useMemo(() => [
    { label: '项目管理', href: '/projects' },
    { label: '需求' },
    { label: requirement?.title ?? '需求详情' },
  ], [requirement?.title])

  if (isLoading) {
    return <div className="container mx-auto px-4 py-6 text-text-muted">加载中...</div>
  }
  if (!requirement) {
    return <div className="container mx-auto px-4 py-6 text-text-muted">需求不存在</div>
  }

  const st = statusMap[requirement.status]
  const pr = priorityMap[requirement.priority]

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
