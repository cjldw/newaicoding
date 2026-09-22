/**
 * ProjectList — 项目列表页
 * 视觉对齐 vp 原型 pageProjects: page-head(h1+sub+acts) + pcards 卡片网格
 * 保留 react-query 数据、新建项目对话框、删除/归档逻辑
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Plus,
  Folder,
  FolderKanban,
  GitBranch,
  FileText,
  Key,
  Archive,
  Trash2,
  Settings,
  MoreHorizontal,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import { useProjectList, useDeleteProject, useArchiveProject } from '@/api/projects'
import type { ProjectListItem } from '@/api/projects'

// 状态徽章颜色映射
const badgeClass: Record<string, string> = {
  active: 'bdg b-green',
  archived: 'bdg b-zinc',
  deleted: 'bdg b-red',
}
const badgeLabel: Record<string, string> = {
  active: '活跃',
  archived: '已归档',
  deleted: '已删除',
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
    <div className="page wide">
      {/* 页头 */}
      <div className="page-head">
        <div>
          <h1 className="flex items-center gap-2"><FolderKanban size={18} /> 项目</h1>
          <div className="sub">
            项目 = 流程与资源的顶层容器,绑定 GitLab 仓库(1 主仓 + N 辅仓)
          </div>
        </div>
        <div className="acts">
          <Link to="/projects/create">
            <button className="btn btn-pri">
              <Plus className="w-4 h-4" />
              新建项目
            </button>
          </Link>
        </div>
      </div>

      {/* 内容 */}
      {isLoading ? (
        <div className="empty">加载中...</div>
      ) : items.length === 0 ? (
        <div className="empty">
          <p>还没有项目</p>
          {/* 用户指令:只保留页头右上角的「新建项目」按钮,空态不再重复放按钮 */}
          <p className="faint" style={{ marginTop: 8 }}>请点击右上角「新建项目」创建第一个项目</p>
        </div>
      ) : (
        <>
          {/* 卡片网格 */}
          <div className="pcards">
            {items.map((item) => {
              const st = badgeClass[item.status] ?? badgeClass.active
              const stLabel = badgeLabel[item.status] ?? badgeLabel.active
              return (
                <div
                  key={item.project_id}
                  className="pcard"
                  onClick={() => (window.location.hash = `#/projects/${item.project_id}`)}
                  role="link"
                  tabIndex={0}
                >
                  <h3>
                    <Folder className="w-[17px] h-[17px]" />
                    {item.name}
                    <span className="chip">{item.slug}</span>
                  </h3>
                  <p>{item.description || '—'}</p>
                  <div className="meta">
                    <span>
                      <GitBranch className="w-[13px] h-[13px]" />
                      {item.repo_count} 个仓库
                    </span>
                    <span>
                      <FileText className="w-[13px] h-[13px]" />
                      0 个需求
                    </span>
                  </div>
                  <div className="foot">
                    <div className="av-stack">
                      <div className="av" style={{ background: '#6366f1' }}>
                        罗
                      </div>
                      <div className="av" style={{ background: '#ec4899' }}>
                        王
                      </div>
                      <div className="av" style={{ background: '#f59e0b' }}>
                        李
                      </div>
                    </div>
                    <span
                      className={`${st} small`}
                      style={{ marginLeft: 'auto' }}
                    >
                      <Key className="w-3 h-3" />
                      {stLabel}
                    </span>
                    {/* 操作菜单 */}
                    <div style={{ position: 'relative', marginLeft: 8 }}>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={(e) => {
                          e.stopPropagation()
                          setActionMenu(
                            actionMenu === item.project_id ? null : item.project_id,
                          )
                        }}
                      >
                        <MoreHorizontal className="w-4 h-4" />
                      </button>
                      {actionMenu === item.project_id && (
                        <div
                          style={{
                            position: 'absolute',
                            right: 0,
                            top: '100%',
                            marginTop: 4,
                            width: 140,
                            background: 'var(--surface)',
                            border: '1px solid var(--border)',
                            borderRadius: 8,
                            boxShadow: 'var(--shadow-md)',
                            zIndex: 10,
                          }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <Link
                            to={`/projects/${item.project_id}?tab=settings`}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              padding: '8px 12px',
                              fontSize: 13,
                              color: 'var(--text)',
                              textDecoration: 'none',
                            }}
                          >
                            <Settings className="w-4 h-4" style={{ marginRight: 8 }} />
                            设置
                          </Link>
                          <button
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              width: '100%',
                              padding: '8px 12px',
                              fontSize: 13,
                              color: 'var(--text)',
                              background: 'transparent',
                              border: 'none',
                              cursor: 'pointer',
                            }}
                            onClick={() => {
                              setConfirmDialog({ type: 'archive', project: item })
                              setActionMenu(null)
                            }}
                          >
                            <Archive className="w-4 h-4" style={{ marginRight: 8 }} />
                            归档
                          </button>
                          <button
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              width: '100%',
                              padding: '8px 12px',
                              fontSize: 13,
                              color: 'var(--error, #b91c1c)',
                              background: 'transparent',
                              border: 'none',
                              cursor: 'pointer',
                            }}
                            onClick={() => {
                              setConfirmDialog({ type: 'delete', project: item })
                              setActionMenu(null)
                            }}
                          >
                            <Trash2 className="w-4 h-4" style={{ marginRight: 8 }} />
                            删除
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          {/* 分页 */}
          {totalPages > 1 && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginTop: 16,
              }}
            >
              <span style={{ fontSize: 13, color: 'var(--muted)' }}>
                共 {total} 个项目,第 {page}/{totalPages} 页
              </span>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  上一页
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
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
