/**
 * TaskCreateDialog — 创建任务对话框
 * props: reqId, type, open, onClose, onSuccess, initialDeployHost
 * 标题根据 type 变化:
 *   dev → 创建开发任务
 *   test → 创建测试任务
 *   release → 创建发布任务
 * 表单: title / description("本次要让 AI 做什么?") / base_branch(可选) / work_branch(可选)
 * release 类型额外字段: deploy_port(10000-10099) / deploy_host(默认 {slug}.{deploy_base_domain})
 * 按钮: 取消 / 创建
 */

import { useState, useEffect } from 'react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { useCreateTask, getTaskErrorMessage } from '@/api/tasks'
import type { CreateTaskPayload, TaskType } from '@/api/tasks'
import { ApiError } from '@/api/client'
import { useCheckPort, isValidHostname } from '@/api/deploy'

interface TaskCreateDialogProps {
  reqId: string
  type: Exclude<TaskType, 'requirement'>
  open: boolean
  onClose: () => void
  onSuccess: (taskId: string) => void
  initialDeployHost?: string
}

const titleMap: Record<string, string> = {
  dev: '创建开发任务',
  test: '创建测试任务',
  release: '创建发布任务',
}

export function TaskCreateDialog({
  reqId, type, open, onClose, onSuccess, initialDeployHost,
}: TaskCreateDialogProps) {
  const createTask = useCreateTask(reqId)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [baseBranch, setBaseBranch] = useState('')
  const [workBranch, setWorkBranch] = useState('')
  const [error, setError] = useState('')

  // release 类型额外字段
  const [deployPort, setDeployPort] = useState('')
  const [deployHost, setDeployHost] = useState('')
  const [portError, setPortError] = useState('')
  const [hostError, setHostError] = useState('')
  const [portToCheck, setPortToCheck] = useState<number | null>(null)
  const portQuery = useCheckPort(portToCheck)

  // 打开时重置表单
  useEffect(() => {
    if (open) {
      setTitle('')
      setDescription('')
      setBaseBranch('')
      setWorkBranch('')
      setError('')
      setDeployPort('')
      setDeployHost(initialDeployHost ?? '')
      setPortError('')
      setHostError('')
      setPortToCheck(null)
    }
  }, [open, initialDeployHost])

  // 端口冲突检查结果
  useEffect(() => {
    if (portQuery.data?.occupied) {
      setPortError('端口已被占用')
    }
  }, [portQuery.data])

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
    if (type === 'release') {
      if (deployPort) payload.deploy_port = Number(deployPort)
      if (deployHost.trim()) payload.deploy_host = deployHost.trim()
    }

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

          {/* release 类型: deploy_port + deploy_host */}
          {type === 'release' && (
            <>
              <div>
                <label className="block text-sm font-medium text-text mb-1.5">
                  部署端口 <span className="text-text-muted text-xs">(10000-10099)</span>
                </label>
                <Input
                  type="number"
                  value={deployPort}
                  onChange={(e) => {
                    setDeployPort(e.target.value)
                    setPortError('')
                  }}
                  onBlur={() => {
                    const n = Number(deployPort)
                    if (deployPort && (n < 10000 || n > 10099)) {
                      setPortError('端口范围 10000-10099')
                    } else if (deployPort) {
                      setPortToCheck(n)
                    }
                  }}
                  placeholder="10000-10099"
                />
                {portError && (
                  <p className="text-xs text-error mt-1">{portError}</p>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-text mb-1.5">
                  部署域名
                </label>
                <Input
                  type="text"
                  value={deployHost}
                  onChange={(e) => {
                    setDeployHost(e.target.value)
                    setHostError('')
                  }}
                  onBlur={() => {
                    if (deployHost.trim() && !isValidHostname(deployHost.trim())) {
                      setHostError('域名格式不合法(不含协议与路径)')
                    }
                  }}
                  placeholder={`默认 {slug}.{部署根域名}(平台设置),可自定义;仅 HTTP,需将域名解析到网关`}
                />
                {hostError && (
                  <p className="text-xs text-error mt-1">{hostError}</p>
                )}
              </div>
            </>
          )}
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
