/**
 * DeployStatus — 部署状态页 /tasks/:taskId/deploy
 * 状态卡片(部署 URL + 状态徽章 + 部署时间)+ 部署日志(只读 Textarea)+ 下线按钮
 */

import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Rocket } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { Textarea } from '@/components/ui/Textarea'
import { Alert } from '@/components/ui/Alert'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/Dialog'
import { useTaskDetail } from '@/api/tasks'
import { useOfflineTask } from '@/api/deploy'

const statusBadge: Record<string, { label: string; variant: 'primary' | 'success' | 'error' }> = {
  deploying: { label: '部署中', variant: 'primary' },
  deployed: { label: '已部署', variant: 'success' },
  failed: { label: '部署失败', variant: 'error' },
}

interface DeployExt {
  deploy_url?: string
  deploy_host?: string
  deploy_port?: number
  deploy_log?: string
  deployed_at?: string
}

export default function DeployStatus({ taskIdProp, embedded = false }: { taskIdProp?: string; embedded?: boolean } = {}) {
  // R4.F4:embedded=true 时被任务工作台中栏「部署日志」Tab 内嵌 —— 用传入 taskId、去掉页壳标题
  const { taskId: routeId = '' } = useParams<{ taskId: string }>()
  const taskId = taskIdProp ?? routeId
  const { data: task } = useTaskDetail(taskId)
  const offlineMut = useOfflineTask(taskId)

  const [showConfirm, setShowConfirm] = useState(false)
  const [toast, setToast] = useState('')

  const ext = (task as unknown as { extended_attributes?: DeployExt }).extended_attributes ?? {}
  const deployUrl = ext.deploy_url ?? ''
  const deployLog = ext.deploy_log ?? ''
  const deployedAt = ext.deployed_at ?? ''
  // 从 task.status 推断部署状态
  const deployStatus = task?.status === 'done' ? 'deployed'
    : task?.status === 'failed' ? 'failed'
    : 'deploying'
  const badge = statusBadge[deployStatus] ?? statusBadge.deploying

  const handleOffline = () => {
    offlineMut.mutate(undefined, {
      onSuccess: () => {
        setShowConfirm(false)
        setToast('已下线')
        setTimeout(() => setToast(''), 3000)
      },
    })
  }

  if (!task) {
    return <div className="page wide text-text-muted">加载中...</div>
  }

  return (
    <div className={embedded ? 'emb-pad' : 'page wide'}>
      {toast && (
        <Alert variant="success" className="mb-4" onClose={() => setToast('')}>
          {toast}
        </Alert>
      )}

      {!embedded && (
        <div className="page-head mb-6">
          {/* R2.F8(BUG-UI-068):页头统一 page-head + icon 惯例 */}
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-text"><Rocket size={18} /> 部署状态</h1>
        </div>
      )}

      {/* 状态卡片 */}
      <Card className="p-6 mb-6">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-muted mb-1">部署 URL</label>
            {deployUrl ? (
              <button
                type="button"
                className="text-primary underline text-sm font-mono hover:opacity-80"
                onClick={() => window.open(deployUrl, '_blank')}
              >
                {deployUrl}
              </button>
            ) : (
              <span className="text-text-muted text-sm">—</span>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-text-muted mb-1">状态</label>
            <Badge variant={badge.variant}>{badge.label}</Badge>
          </div>
          <div>
            <label className="block text-sm font-medium text-text-muted mb-1">部署时间</label>
            <span className="text-text text-sm">
              {deployedAt ? new Date(deployedAt).toLocaleString('zh-CN') : '—'}
            </span>
          </div>
        </div>
      </Card>

      {/* 部署日志 */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-text-muted mb-1.5">部署日志</label>
        <Textarea
          value={deployLog}
          readOnly
          rows={12}
          className="font-mono text-xs"
          placeholder=""
        />
      </div>

      {/* 下线按钮 */}
      {deployStatus === 'deployed' && (
        <div className="flex justify-end">
          <Button
            variant="danger"
            onClick={() => setShowConfirm(true)}
          >
            下线
          </Button>
        </div>
      )}

      {/* 下线确认对话框 */}
      <Dialog open={showConfirm} onOpenChange={setShowConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认下线</DialogTitle>
            <DialogDescription>
              确定下线吗?下线后 URL 将不可访问
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowConfirm(false)}>
              取消
            </Button>
            <Button
              variant="danger"
              onClick={handleOffline}
              disabled={offlineMut.isPending}
            >
              {offlineMut.isPending ? '下线中...' : '确定'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
