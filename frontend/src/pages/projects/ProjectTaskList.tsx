/**
 * ProjectTaskList — 项目级任务列表(R26:项目详情页任务 tab)
 * 按需求分组显示,支持状态筛选与搜索
 * 创建任务:点击"创建任务"→ 选需求 → 弹出 TaskCreateDialog
 * 风格对齐 RequirementList
 */

import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, Filter, ChevronDown, ChevronRight, FolderKanban, CheckCircle2, XCircle, Clock, Loader2, Plus } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useProjectTaskList, type TaskListItem, type TaskStatus } from '@/api/tasks'
import { RequirementPickerDialog } from './RequirementPickerDialog'
import { TaskCreateDialog } from '../tasks/TaskCreateDialog'
import type { TaskType } from '@/api/tasks'

interface ProjectTaskListProps {
  projectId: string
}

const statusMap: Record<TaskStatus, { label: string; variant: 'success' | 'default' | 'error' | 'warning' }> = {
  pending: { label: '等待中', variant: 'default' },
  running: { label: '运行中', variant: 'warning' },
  done: { label: '已完成', variant: 'success' },
  failed: { label: '失败', variant: 'error' },
  cancelled: { label: '已取消', variant: 'default' },
  timeout: { label: '超时', variant: 'error' },
  cases_review: { label: '用例审查', variant: 'warning' },
}

const typeMap: Record<string, string> = {
  dev: '开发',
  test: '测试',
  release: '发布',
  requirement: '需求',
}

export function ProjectTaskList({ projectId }: ProjectTaskListProps) {
  const navigate = useNavigate()
  const { data, isLoading } = useProjectTaskList(projectId)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all')
  const [expandedReqs, setExpandedReqs] = useState<Set<string>>(new Set())

  // 创建任务流程:选需求 → 选类型 → 创建
  const [pickerOpen, setPickerOpen] = useState(false)
  const [selectedReq, setSelectedReq] = useState<{ id: string; title: string } | null>(null)
  const [createType, setCreateType] = useState<Exclude<TaskType, 'requirement'> | null>(null)

  const handleReqSelect = (reqId: string, reqTitle: string) => {
    setPickerOpen(false)
    setSelectedReq({ id: reqId, title: reqTitle })
    setCreateType('dev') // 默认 dev 类型
  }

  const handleTaskCreated = (taskId: string) => {
    setCreateType(null)
    setSelectedReq(null)
    navigate(`/tasks/${taskId}`)
  }

  // 按需求分组
  const grouped = useMemo(() => {
    if (!data?.items) return []
    const map = new Map<string, { reqId: string; reqTitle: string; tasks: TaskListItem[] }>()
    for (const task of data.items) {
      const reqId = task.req_id || 'unknown'
      const reqTitle = task.req_title || '未知需求'
      if (!map.has(reqId)) {
        map.set(reqId, { reqId, reqTitle, tasks: [] })
      }
      map.get(reqId)!.tasks.push(task)
    }
    return Array.from(map.values())
  }, [data])

  // 过滤
  const filtered = useMemo(() => {
    return grouped
      .map((group) => ({
        ...group,
        tasks: group.tasks.filter((t) => {
          if (statusFilter !== 'all' && t.status !== statusFilter) return false
          if (search && !t.title.toLowerCase().includes(search.toLowerCase())) return false
          return true
        }),
      }))
      .filter((g) => g.tasks.length > 0)
  }, [grouped, statusFilter, search])

  const toggleReq = (reqId: string) => {
    const next = new Set(expandedReqs)
    if (next.has(reqId)) next.delete(reqId)
    else next.add(reqId)
    setExpandedReqs(next)
  }

  if (isLoading) {
    return <div className="text-center py-12 text-text-muted">加载中...</div>
  }

  const hasTasks = !!data?.items?.length

  return (
    <div className="space-y-4">
      {/* 工具栏 */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <Input
            placeholder="搜索任务..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="relative">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as any)}
            className="appearance-none pl-8 pr-8 py-2 text-sm border border-border rounded-md bg-surface cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary/20"
          >
            <option value="all">全部状态</option>
            <option value="pending">等待中</option>
            <option value="running">运行中</option>
            <option value="done">已完成</option>
            <option value="failed">失败</option>
            <option value="cancelled">已取消</option>
            <option value="timeout">超时</option>
            <option value="cases_review">用例审查</option>
          </select>
          <Filter className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted pointer-events-none" />
          <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted pointer-events-none" />
        </div>
        {hasTasks && (
          <div className="text-sm text-text-muted">
            共 {data.items.length} 个任务
          </div>
        )}
        <div className="flex-1" />
        <Button variant="primary" onClick={() => setPickerOpen(true)}>
          <Plus className="w-4 h-4 mr-2" />
          创建任务
        </Button>
      </div>

      {/* 任务列表(按需求分组) */}
      {hasTasks ? (
        <div className="space-y-3">
          {filtered.map((group) => (
            <div key={group.reqId} className="border border-border rounded-lg overflow-hidden">
              {/* 需求标题 */}
              <button
                onClick={() => toggleReq(group.reqId)}
                className="w-full flex items-center gap-2 px-4 py-2.5 bg-surface-strong hover:bg-surface-strong/80 transition-colors text-left"
              >
                {expandedReqs.has(group.reqId) ? (
                  <ChevronDown className="w-4 h-4 text-text-muted" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-text-muted" />
                )}
                <FolderKanban className="w-4 h-4 text-text-muted" />
                <span className="text-sm font-medium text-text">{group.reqTitle}</span>
                <Badge variant="default" className="ml-auto">
                  {group.tasks.length}
                </Badge>
              </button>

              {/* 任务列表 */}
              {expandedReqs.has(group.reqId) && (
                <div className="divide-y divide-border">
                  {group.tasks.map((task) => {
                    const st = statusMap[task.status] || statusMap.pending
                    return (
                      <div
                        key={task.task_id}
                        onClick={() => navigate(`/tasks/${task.task_id}`)}
                        className="flex items-center gap-3 px-4 py-3 hover:bg-surface-strong/50 cursor-pointer transition-colors"
                      >
                        {/* 状态图标 */}
                        {task.status === 'done' && <CheckCircle2 className="w-4 h-4 text-green-500" />}
                        {task.status === 'failed' && <XCircle className="w-4 h-4 text-red-500" />}
                        {task.status === 'running' && <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />}
                        {(task.status === 'pending' || task.status === 'cancelled' || task.status === 'timeout') && (
                          <Clock className="w-4 h-4 text-text-muted" />
                        )}
                        {task.status === 'cases_review' && <Clock className="w-4 h-4 text-orange-500" />}

                        {/* 任务信息 */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-text truncate">{task.title}</span>
                            <Badge variant="default" className="text-xs">
                              {typeMap[task.type] || task.type}
                            </Badge>
                          </div>
                          <div className="flex items-center gap-2 mt-0.5 text-xs text-text-muted">
                            <span>{task.created_by?.nickname || '未知'}</span>
                            <span>·</span>
                            <span>{new Date(task.created_at).toLocaleDateString()}</span>
                          </div>
                        </div>

                        {/* 状态徽章 */}
                        <Badge variant={st.variant}>{st.label}</Badge>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          ))}

          {filtered.length === 0 && (
            <div className="text-center py-8 text-text-muted">
              没有匹配的任务
            </div>
          )}
        </div>
      ) : (
        /* 空态:带创建入口 */
        <div className="text-center py-12 text-text-muted">
          <FolderKanban className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>暂无任务</p>
          <p className="text-sm mt-1">点击「创建任务」,选择需求后即可创建</p>
        </div>
      )}

      {/* 需求选择对话框 */}
      <RequirementPickerDialog
        projectId={projectId}
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={handleReqSelect}
      />

      {/* 任务创建对话框 */}
      {selectedReq && createType && (
        <TaskCreateDialog
          reqId={selectedReq.id}
          type={createType}
          open={!!selectedReq}
          onClose={() => { setSelectedReq(null); setCreateType(null) }}
          onSuccess={handleTaskCreated}
        />
      )}
    </div>
  )
}
