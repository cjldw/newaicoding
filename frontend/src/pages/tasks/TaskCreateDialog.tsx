/**
 * TaskCreateDialog — 创建任务对话框
 * props: reqId, type, open, onClose, onSuccess
 * 标题根据 type 变化:
 *   dev → 创建开发任务
 *   test → 创建测试任务
 *   release → 创建发布任务
 * 表单: title / description("本次要让 AI 做什么?") / base_branch(可选) / work_branch(可选)
 * 按钮: 取消 / 创建
 */

import { useState, useEffect } from 'react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/Textarea'
import { useCreateTask, getTaskErrorMessage } from '@/api/tasks'
import type { CreateTaskPayload, TaskType } from '@/api/tasks'
import { ApiError } from '@/api/client'

interface TaskCreateDialogProps {
  reqId: string
  type: Exclude<TaskType, 'requirement'>
  open: boolean
  onClose: () => void
  onSuccess: (taskId: string) => void
}

const titleMap: Record<string, string> = {
  dev: '创建开发任务',
  test: '创建测试任务',
  release: '创建发布任务',
}

export function TaskCreateDialog({
  reqId, type, open, onClose, onSuccess,
}: TaskCreateDialogProps) {
  const createTask = useCreateTask(reqId)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [baseBranch, setBaseBranch] = useState('')
  const [workBranch, setWorkBranch] = useState('')
  const [error, setError] = useState('')

  // 打开时重置表单
  useEffect(() => {
    if (open) {
      setTitle('')
      setDescription('')
      setBaseBranch('')
      setWorkBranch('')
      setError('')
    }
  }, [open])

  const handleCreate = () => {
    if (!title.trim()) {
      setError('请填写任务标题')
      return
    }
    if (!description.trim()) {
      setError('请填写任务描述')
      return
    }

    const payload: CreateTaskPayload = {
      type,
      title: title.trim(),
      description: description.trim(),
    }
    if (baseBranch.trim()) payload.base_branch = baseBranch.trim()
    if (workBranch.trim()) payload.work_branch = workBranch.trim()

    createTask.mutate(payload, {
      onSuccess: (data) => {
        onSuccess(data.task_id)
        onClose()
      },
      onError: (err) => {
        const code = err instanceof ApiError ? err.code : 0
        setError(getTaskErrorMessage(code, '创建失败,请重试'))
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{titleMap[type] ?? '创建任务'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* 错误提示 */}
          {error && (
            <div className="p-3 bg-error/10 border border-error/20 rounded-md text-sm text-error">
              {error}
            </div>
          )}

          {/* 标题 */}
          <div>
            <label className="block text-sm font-medium text-text mb-1.5">
              任务标题 <span className="text-error">*</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例如: 实现用户登录功能"
              className="w-full px-3 py-2 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          {/* 描述 */}
          <div>
            <label className="block text-sm font-medium text-text mb-1.5">
              任务描述 <span className="text-error">*</span>
            </label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="本次要让 AI 做什么?"
              rows={4}
            />
          </div>

          {/* base_branch */}
          <div>
            <label className="block text-sm font-medium text-text mb-1.5">
              基础分支 <span className="text-text-muted text-xs">(可选)</span>
            </label>
            <input
              type="text"
              value={baseBranch}
              onChange={(e) => setBaseBranch(e.target.value)}
              placeholder="默认: main"
              className="w-full px-3 py-2 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-primary font-mono"
            />
          </div>

          {/* work_branch */}
          <div>
            <label className="block text-sm font-medium text-text mb-1.5">
              工作分支 <span className="text-text-muted text-xs">(可选)</span>
            </label>
            <input
              type="text"
              value={workBranch}
              onChange={(e) => setWorkBranch(e.target.value)}
              placeholder="自动生成"
              className="w-full px-3 py-2 text-sm bg-background border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-primary font-mono"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={createTask.isPending}>
            取消
          </Button>
          <Button
            variant="primary"
            onClick={handleCreate}
            disabled={createTask.isPending || !title.trim() || !description.trim()}
          >
            {createTask.isPending ? '创建中...' : '创建'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
