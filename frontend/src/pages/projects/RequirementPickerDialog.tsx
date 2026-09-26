/**
 * RequirementPickerDialog — 需求选择对话框
 * 用于项目级任务创建时选择目标需求
 * 风格对齐 RequirementList 的 Dialog 用法
 */

import { useState } from 'react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { useRequirementList } from '@/api/requirements'
import { FolderOpen, Search } from 'lucide-react'

interface RequirementPickerDialogProps {
  projectId: string
  open: boolean
  onClose: () => void
  onSelect: (reqId: string, reqTitle: string) => void
}

interface Requirement {
  req_id: string
  title: string
  status: string
}

export function RequirementPickerDialog({
  projectId, open, onClose, onSelect,
}: RequirementPickerDialogProps) {
  const { data, isLoading } = useRequirementList(projectId, { page: 1, page_size: 100 })
  const [search, setSearch] = useState('')

  const requirements = (data?.items || []) as Requirement[]

  const filtered = requirements.filter((req) =>
    req.title.toLowerCase().includes(search.toLowerCase())
  )

  const statusMap: Record<string, { label: string; variant: 'success' | 'default' | 'error' | 'warning' }> = {
    drafting: { label: '打磨中', variant: 'default' },
    dev_ready: { label: '待开发', variant: 'success' },
    in_dev: { label: '开发中', variant: 'warning' },
    testing: { label: '测试中', variant: 'warning' },
    done: { label: '已完成', variant: 'success' },
    archived: { label: '已归档', variant: 'default' },
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>选择需求</DialogTitle>
          <DialogDescription>
            选择一个需求来创建任务。任务必须关联到具体需求。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* 搜索框 */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
            <Input
              placeholder="搜索需求..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>

          {/* 需求列表 */}
          <div className="max-h-96 overflow-y-auto border border-border rounded-md">
            {isLoading ? (
              <div className="text-center py-8 text-text-muted">加载中...</div>
            ) : filtered.length === 0 ? (
              <div className="text-center py-8 text-text-muted">
                {search ? '没有匹配的需求' : '暂无需求'}
              </div>
            ) : (
              <div className="divide-y divide-border">
                {filtered.map((req) => {
                  const st = statusMap[req.status] || { label: req.status, variant: 'default' as const }
                  return (
                    <button
                      key={req.req_id}
                      onClick={() => onSelect(req.req_id, req.title)}
                      className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-strong/50 transition-colors text-left"
                    >
                      <FolderOpen className="w-4 h-4 text-text-muted flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-text truncate">
                          {req.title}
                        </div>
                      </div>
                      <Badge variant={st.variant}>{st.label}</Badge>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
