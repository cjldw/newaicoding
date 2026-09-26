/**
 * ProjectDetail — 项目详情页
 * 页头(名称+状态徽章+设置/归档/删除)+ Tab 导航
 * 本阶段仅"仓库"Tab 可用,其余 disabled
 */

import { useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { Settings, Archive, Trash2, MoreHorizontal, FolderKanban } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import { useProjectDetail, useDeleteProject, useArchiveProject } from '@/api/projects'
import { RepoManagement } from './RepoManagement'
import { MemberManagement } from './MemberManagement'
import { ModelConfigManagement } from './ModelConfigManagement'
import { McpConfigManagement } from './McpConfigManagement'
import { SkillsManagement } from './SkillsManagement'
import { RequirementList } from '../requirements/RequirementList'

const statusMap: Record<string, { label: string; variant: 'success' | 'default' | 'error' }> = {
  active: { label: '活跃', variant: 'success' },
  archived: { label: '已归档', variant: 'default' },
  deleted: { label: '已删除', variant: 'error' },
}

const tabs = [
  { key: 'requirements', label: '需求', disabled: false },
  { key: 'tasks', label: '任务', disabled: true },
  { key: 'repos', label: '仓库', disabled: false },
  { key: 'members', label: '成员', disabled: false },
  { key: 'settings', label: '设置', disabled: false },
]

export function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { data: project, isLoading } = useProjectDetail(projectId ?? '')
  const deleteProject = useDeleteProject()
  const archiveProject = useArchiveProject()

  const [actionMenu, setActionMenu] = useState(false)
  const [confirmDialog, setConfirmDialog] = useState<'delete' | 'archive' | null>(null)
  const [settingsTab, setSettingsTab] = useState<'mcp' | 'skills' | 'model'>('mcp')

  const activeTab = searchParams.get('tab') ?? 'requirements'
  const st = project ? (statusMap[project.status] ?? statusMap.active) : statusMap.active

  function handleConfirm() {
    if (!projectId || !confirmDialog) return
    if (confirmDialog === 'delete') {
      deleteProject.mutate(projectId, { onSuccess: () => navigate('/projects') })
    } else {
      archiveProject.mutate(projectId)
    }
    setConfirmDialog(null)
  }

  if (isLoading) {
    return <div className="page wide text-text-muted">加载中...</div>
  }
  if (!project) {
    return <div className="page wide text-text-muted">项目不存在</div>
  }

  return (
    <div className="page wide">
      {/* 页头 */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          {/* R2.F8(BUG-UI-068):h1 补 icon 惯例 */}
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-text"><FolderKanban size={18} /> {project.name}</h1>
          <Badge variant={st.variant}>{st.label}</Badge>
        </div>
        <div className="relative">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setActionMenu(!actionMenu)}
          >
            <MoreHorizontal className="w-4 h-4" />
          </Button>
          {actionMenu && (
            <div className="absolute right-0 top-full mt-1 w-32 bg-surface border border-border rounded-md shadow-lg z-10">
              <button
                className="flex items-center w-full px-3 py-2 text-sm hover:bg-surface-strong text-text"
                // BUG-011:接线设置入口(早期占位空 onClick 导致 MCP/Skills/模型配置不可达)
                onClick={() => { setActionMenu(false); navigate('?tab=settings') }}
              >
                <Settings className="w-4 h-4 mr-2" />
                设置
              </button>
              <button
                className="flex items-center w-full px-3 py-2 text-sm hover:bg-surface-strong text-text"
                onClick={() => { setActionMenu(false); setConfirmDialog('archive') }}
              >
                <Archive className="w-4 h-4 mr-2" />
                归档
              </button>
              <button
                className="flex items-center w-full px-3 py-2 text-sm hover:bg-surface-strong text-red-fg"
                onClick={() => { setActionMenu(false); setConfirmDialog('delete') }}
              >
                <Trash2 className="w-4 h-4 mr-2" />
                删除
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Tab 导航 */}
      <div className="border-b border-border mb-6">
        <nav className="flex gap-6">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              disabled={tab.disabled}
              onClick={() => !tab.disabled && navigate(`?tab=${tab.key}`)}
              className={`pb-2 text-sm font-medium border-b-2 transition-colors ${
                tab.disabled
                  ? 'text-text-muted/50 cursor-not-allowed border-transparent'
                  : activeTab === tab.key
                    ? 'text-primary border-primary'
                    : 'text-text-muted border-transparent hover:text-text'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab 内容 */}
      {activeTab === 'requirements' && <RequirementList />}
      {activeTab === 'repos' && <RepoManagement projectId={project.project_id} />}
      {activeTab === 'members' && <MemberManagement projectId={project.project_id} />}
      {activeTab === 'settings' && (
        <div className="space-y-4">
          {/* 设置子导航 */}
          <div className="flex gap-2 border-b border-border pb-2">
            {([
              { key: 'mcp' as const, label: 'MCP 配置' },
              { key: 'skills' as const, label: 'Skills 管理' },
              { key: 'model' as const, label: '模型配置' },
            ]).map((sub) => (
              <button
                key={sub.key}
                onClick={() => setSettingsTab(sub.key)}
                className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                  settingsTab === sub.key
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'text-text-muted hover:text-text hover:bg-surface-strong'
                }`}
              >
                {sub.label}
              </button>
            ))}
          </div>
          {/* 子 Tab 内容 */}
          {settingsTab === 'mcp' && <McpConfigManagement projectId={project.project_id} />}
          {settingsTab === 'skills' && <SkillsManagement projectId={project.project_id} />}
          {settingsTab === 'model' && <ModelConfigManagement projectId={project.project_id} />}
        </div>
      )}
      {activeTab !== 'requirements' && activeTab !== 'repos' && activeTab !== 'members' && activeTab !== 'settings' && (
        <div className="text-center py-12 text-text-muted">
          该功能暂未开放
        </div>
      )}

      {/* 确认对话框 */}
      <Dialog open={!!confirmDialog} onOpenChange={() => setConfirmDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {confirmDialog === 'archive' ? '归档项目' : '删除项目'}
            </DialogTitle>
            <DialogDescription>
              {confirmDialog === 'archive'
                ? `确定要归档项目「${project.name}」吗?归档后项目将不再活跃显示。`
                : `确定要删除项目「${project.name}」吗?此操作不可恢复。`}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmDialog(null)}>
              取消
            </Button>
            <Button
              variant={confirmDialog === 'delete' ? 'danger' : 'primary'}
              onClick={handleConfirm}
            >
              {confirmDialog === 'delete' ? '删除' : '归档'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
