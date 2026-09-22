/**
 * RequirementList — 需求列表页
 * 标题"需求" + 主按钮"新建需求" + 表格 + 分页 + 空态 + 创建对话框
 */

import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Plus, Eye } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
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
  })
  const [formError, setFormError] = useState('')

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
    <div className="page wide">
      {/* 页头 */}
      <div className="page-head">
        <h1 className="text-2xl font-semibold text-text">需求</h1>
        <Button variant="primary" onClick={() => setShowCreateDialog(true)}>
          <Plus className="w-4 h-4 mr-2" />
          新建需求
        </Button>
      </div>

      {/* 表格 */}
      {isLoading ? (
        <div className="text-center py-12 text-text-muted">加载中...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-text-muted mb-4">暂无需求</p>
          <Button variant="primary" onClick={() => setShowCreateDialog(true)}>
            <Plus className="w-4 h-4 mr-2" />
            新建需求
          </Button>
        </div>
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
                <TableHead className="w-[80px]">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => {
                const st = statusMap[item.status]
                const pr = priorityMap[item.priority]
                return (
                  <TableRow key={item.req_id}>
                    <TableCell className="font-medium text-text">
                      {item.title}
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
                    <TableCell>
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
          </div>

          {/* 分页 */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <span className="text-sm text-text-muted">
                共 {total} 个需求,第 {page}/{totalPages} 页
              </span>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage(p => p - 1)}
                >
                  上一页
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage(p => p + 1)}
                >
                  下一页
                </Button>
              </div>
            </div>
          )}
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
                标题 <span className="text-error">*</span>
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
                描述 <span className="text-error">*</span>
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
            {formError && (
              <div className="text-sm text-error">{formError}</div>
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
