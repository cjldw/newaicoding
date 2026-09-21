/**
 * ProjectList — 项目列表页
 * 标题"我的项目" + 主按钮"新建项目" + 表格 + 分页 + 空态
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, MoreHorizontal, Archive, Trash2, Settings } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import { useProjectList, useDeleteProject, useArchiveProject } from '@/api/projects'
import type { ProjectListItem } from '@/api/projects'

// 状态徽章映射
const statusMap: Record<string, { label: string; variant: 'success' | 'default' | 'error' }> = {
  active: { label: '活跃', variant: 'success' },
  archived: { label: '已归档', variant: 'default' },
  deleted: { label: '已删除', variant: 'error' },
}

export function ProjectList() {
  const [page, setPage] = useState(1)
  const { data, isLoading } = useProjectList({ status: 'active', page, page_size: 10 })
  const deleteProject = useDeleteProject()
  const archiveProject = useArchiveProject()
  const [actionMenu, setActionMenu] = useState<string | null>(null)
  const [confirmDialog, setConfirmDialog] = useState<{
    type: 'delete' | 'archive'
    project: ProjectListItem
  } | null>(null)

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pageSize = 10
  const totalPages = Math.ceil(total / pageSize)

  function handleConfirm() {
    if (!confirmDialog) return
    if (confirmDialog.type === 'delete') {
      deleteProject.mutate(confirmDialog.project.project_id)
    } else {
      archiveProject.mutate(confirmDialog.project.project_id)
    }
    setConfirmDialog(null)
  }

  return (
    <div className="container mx-auto px-4 py-6">
      {/* 页头 */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-text">我的项目</h1>
        <Link to="/projects/create">
          <Button variant="primary">
            <Plus className="w-4 h-4 mr-2" />
            新建项目
          </Button>
        </Link>
      </div>

      {/* 表格 */}
      {isLoading ? (
        <div className="text-center py-12 text-text-muted">加载中...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-text-muted mb-4">还没有项目</p>
          <Link to="/projects/create">
            <Button variant="primary">
              <Plus className="w-4 h-4 mr-2" />
              新建项目
            </Button>
          </Link>
        </div>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>项目名称</TableHead>
                <TableHead>描述</TableHead>
                <TableHead>仓库数</TableHead>
                <TableHead>创建时间</TableHead>
                <TableHead>状态</TableHead>
                <TableHead className="w-[80px]">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => {
                const st = statusMap[item.status] ?? statusMap.active
                return (
                  <TableRow key={item.project_id}>
                    <TableCell>
                      <Link
                        to={`/projects/${item.project_id}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {item.name}
                      </Link>
                      <div className="text-xs text-text-muted">{item.slug}</div>
                    </TableCell>
                    <TableCell className="text-text-muted">
                      {item.description || '—'}
                    </TableCell>
                    <TableCell>{item.repo_count}</TableCell>
                    <TableCell className="text-text-muted">
                      {new Date(item.created_at).toLocaleDateString('zh-CN')}
                    </TableCell>
                    <TableCell>
                      <Badge variant={st.variant}>{st.label}</Badge>
                    </TableCell>
                    <TableCell>
                      <div className="relative">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setActionMenu(actionMenu === item.project_id ? null : item.project_id)}
                        >
                          <MoreHorizontal className="w-4 h-4" />
                        </Button>
                        {actionMenu === item.project_id && (
                          <div className="absolute right-0 top-full mt-1 w-32 bg-surface border border-border rounded-md shadow-lg z-10">
                            <Link
                              to={`/projects/${item.project_id}?tab=settings`}
                              className="flex items-center px-3 py-2 text-sm hover:bg-surface-strong text-text"
                            >
                              <Settings className="w-4 h-4 mr-2" />
                              设置
                            </Link>
                            <button
                              className="flex items-center w-full px-3 py-2 text-sm hover:bg-surface-strong text-text"
                              onClick={() => {
                                setConfirmDialog({ type: 'archive', project: item })
                                setActionMenu(null)
                              }}
                            >
                              <Archive className="w-4 h-4 mr-2" />
                              归档
                            </button>
                            <button
                              className="flex items-center w-full px-3 py-2 text-sm hover:bg-surface-strong text-error"
                              onClick={() => {
                                setConfirmDialog({ type: 'delete', project: item })
                                setActionMenu(null)
                              }}
                            >
                              <Trash2 className="w-4 h-4 mr-2" />
                              删除
                            </button>
                          </div>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>

          {/* 分页 */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <span className="text-sm text-text-muted">
                共 {total} 个项目,第 {page}/{totalPages} 页
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

      {/* 确认对话框 */}
      <Dialog open={!!confirmDialog} onOpenChange={() => setConfirmDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {confirmDialog?.type === 'archive' ? '归档项目' : '删除项目'}
            </DialogTitle>
            <DialogDescription>
              {confirmDialog?.type === 'archive'
                ? `确定要归档项目「${confirmDialog?.project.name}」吗?归档后项目将不再活跃显示。`
                : `确定要删除项目「${confirmDialog?.project.name}」吗?此操作不可恢复。`}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmDialog(null)}>
              取消
            </Button>
            <Button
              variant={confirmDialog?.type === 'delete' ? 'primary' : 'default'}
              className={confirmDialog?.type === 'delete' ? 'bg-error hover:bg-error/90' : ''}
              onClick={handleConfirm}
            >
              {confirmDialog?.type === 'delete' ? '删除' : '归档'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
