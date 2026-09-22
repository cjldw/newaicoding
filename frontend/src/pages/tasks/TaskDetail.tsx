/**
 * TaskDetail — 任务工作台(R4)
 * 三栏布局:左侧文件树 250px(全部/变更双视图)+ 中间编辑器/Diff/预览自适应 + 右侧对话框 400px
 */

import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Square, RotateCcw, CheckCircle2, ClipboardList, FileText } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import CodeEditor from '@/components/Editor'
import DiffViewer from '@/components/DiffViewer'
import FileTree from '@/components/FileTree'
import { PreviewPanel } from '@/components/PreviewPanel'
import { TerminalPanel } from '@/components/TerminalPanel'
import { TaskChat } from '@/components/TaskChat'
import { ActivityStream } from '@/components/ActivityStream'
import {
  useTaskDetail, useStopTask, useRetryTask, useTaskPreviews,
} from '@/api/tasks'
import {
  useTaskFiles, useTaskFileContent, useUpdateTaskFileContent,
  useTaskDiff, useTaskChanges,
} from '@/api/files'
import { createTerminalSession } from '@/api/terminal'

const statusBadge: Record<string, { label: string; variant: 'default' | 'primary' | 'success' | 'error' | 'secondary' | 'outline' }> = {
  pending: { label: '等待中', variant: 'outline' },
  running: { label: '运行中', variant: 'primary' },
  done: { label: '已完成', variant: 'success' },
  failed: { label: '失败', variant: 'error' },
  cancelled: { label: '已取消', variant: 'secondary' },
  timeout: { label: '超时', variant: 'error' },
  cases_review: { label: '用例审阅', variant: 'primary' },
}

const typeBadge: Record<string, { label: string; variant: 'default' | 'primary' | 'success' | 'secondary' }> = {
  requirement: { label: '需求打磨', variant: 'secondary' },
  dev: { label: '开发', variant: 'primary' },
  test: { label: '测试', variant: 'primary' },
  release: { label: '发布', variant: 'success' },
}

type CenterView = 'editor' | 'diff' | 'preview'

export default function TaskDetail() {
  const { taskId = '' } = useParams<{ taskId: string }>()
  const nav = useNavigate()
  const { data: task } = useTaskDetail(taskId)
  const { data: previews } = useTaskPreviews(taskId)
  const stopTask = useStopTask(taskId)
  const retryTask = useRetryTask(taskId)

  // 文件树数据(R11 hooks;根目录 + 变更清单)
  const { data: filesData, refetch: refetchFiles } = useTaskFiles(taskId, '/workspace/main')
  const { data: changesData, refetch: refetchChanges } = useTaskChanges(taskId)

  // 文件内容与保存
  const [selectedPath, setSelectedPath] = useState('')
  const [enabled, setEnabled] = useState(false) // 点选文件后才拉内容
  const { data: fileData } = useTaskFileContent(taskId, enabled ? selectedPath : '')
  const saveFile = useUpdateTaskFileContent()

  // Diff
  const { data: diffData } = useTaskDiff(taskId)
  const [diffPath, setDiffPath] = useState<string | null>(null)

  const [centerView, setCenterView] = useState<CenterView>('editor')

  const st = task ? (statusBadge[task.status] ?? statusBadge.pending) : statusBadge.pending
  const tp = task ? (typeBadge[task.type] ?? typeBadge.dev) : typeBadge.dev
  const previewItem: { port: number; preview_url: string; status: string } | null =
    (previews as unknown as { items?: { port: number; preview_url: string; status: string }[] })?.items?.[0] ?? null

  // watcher 无轮询时兜底:每 15s 刷新变更列表(running 时)
  useEffect(() => {
    if (task?.status !== 'running') return
    const timer = setInterval(() => refetchChanges(), 15000)
    return () => clearInterval(timer)
  }, [task?.status, refetchChanges])

  function currentDiff(): { old: string; new: string } {
    const files = diffData?.files ?? []
    const hit = files.find((f) => f.path === diffPath)
    if (!hit) return { old: '', new: '' }
    const oldLines: string[] = []
    const newLines: string[] = []
    for (const ln of hit.diff.split('\n')) {
      if (ln.startsWith('-') && !ln.startsWith('---')) oldLines.push(ln.slice(1))
      else if (ln.startsWith('+') && !ln.startsWith('+++')) newLines.push(ln.slice(1))
      else if (!ln.startsWith('@@')) { oldLines.push(ln.replace(/^ /, '')); newLines.push(ln.replace(/^ /, '')) }
    }
    return { old: oldLines.join('\n'), new: newLines.join('\n') }
  }

  if (!task) {
    return <div className="page wide text-text-muted">加载中...</div>
  }

  return (
    <div className="h-screen flex flex-col">
      {/* 任务头 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold text-text">{task.title}</h1>
          <Badge variant={tp.variant}>{tp.label}</Badge>
          <Badge variant={st.variant}>{st.label}</Badge>
          {task.error_message && <span className="text-xs text-error">{task.error_message}</span>}
        </div>
        <div className="flex items-center gap-2">
          {(task.status === 'running' || task.status === 'pending') && (
            <Button variant="outline" size="sm" onClick={() => stopTask.mutate()}>
              <Square className="w-4 h-4 mr-1" /> 停止
            </Button>
          )}
          {['failed', 'cancelled', 'timeout'].includes(task.status) && (
            <Button variant="outline" size="sm" onClick={() => retryTask.mutate()}>
              <RotateCcw className="w-4 h-4 mr-1" /> 重试
            </Button>
          )}
          {task.status === 'running' && (
            <Button
              variant="primary" size="sm"
              onClick={() => { refetchChanges(); setCenterView('diff') }}
            >
              <CheckCircle2 className="w-4 h-4 mr-1" /> 查看 Diff
            </Button>
          )}
          {(task.status === 'cases_review' || task.type === 'test') && (
            <Button
              variant="outline" size="sm"
              onClick={() => nav(`/tasks/${taskId}/cases`)}
            >
              <ClipboardList className="w-4 h-4 mr-1" /> 用例审阅
            </Button>
          )}
          {(task.status === 'done' && task.type === 'test') && (
            <Button
              variant="outline" size="sm"
              onClick={() => nav(`/tasks/${taskId}/report`)}
            >
              <FileText className="w-4 h-4 mr-1" /> 测试报告
            </Button>
          )}
        </div>
      </div>

      {/* 三栏主体 */}
      <div className="flex-1 flex min-h-0">
        {/* 左:文件树 */}
        <div className="w-[250px] shrink-0 border-r border-border overflow-y-auto">
          <FileTree
            mode="task"
            files={filesData?.items ?? []}
            changes={changesData?.repos ?? []}
            selectedPath={selectedPath}
            onSelectFile={(p) => { setSelectedPath(p); setEnabled(true); setCenterView('editor') }}
            onSelectDiff={(p) => { setDiffPath(p); setCenterView('diff') }}
            onRefresh={() => { refetchFiles(); refetchChanges() }}
          />
        </div>

        {/* 中:编辑器 / Diff / 预览 */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="px-3 py-2 border-b border-border flex gap-4">
            {(['editor', 'diff', 'preview'] as CenterView[]).map((v) => (
              <button
                key={v}
                onClick={() => setCenterView(v)}
                className={`text-sm font-medium pb-1 border-b-2 transition-colors ${
                  centerView === v
                    ? 'text-primary border-primary'
                    : 'text-text-muted border-transparent hover:text-text'
                }`}
              >
                {v === 'editor' ? '编辑器' : v === 'diff' ? 'Diff 视图' : '预览'}
              </button>
            ))}
          </div>
          <div className="flex-1 min-h-0 flex flex-col">
            {centerView === 'editor' && (
              selectedPath ? (
                <CodeEditor
                  value={fileData?.content ?? ''}
                  path={selectedPath}
                  onSave={(v) => saveFile.mutate({ taskId, path: selectedPath, content: v })}
                  onChange={() => {}}
                />
              ) : (
                <div className="flex-1 flex items-center justify-center text-text-muted">在左侧选择文件</div>
              )
            )}
            {centerView === 'diff' && (
              diffPath ? (
                (() => { const d = currentDiff(); return (
                  <DiffViewer oldValue={d.old} newValue={d.new} oldTitle={diffPath} newTitle={diffPath} />
                ) })()
              ) : (
                <div className="flex-1 flex items-center justify-center text-text-muted">在左侧变更列表选择文件</div>
              )
            )}
            {centerView === 'preview' && <PreviewPanel previewUrl={previewItem?.preview_url ?? null} />}
          </div>
        </div>

        {/* 右:对话框 + 活动流/终端 */}
        <div className="w-[400px] shrink-0 border-l border-border flex flex-col min-h-0">
          <div className="flex-1 min-h-0 overflow-hidden">
            <TaskChat taskId={taskId} />
          </div>
          <div className="h-[320px] border-t border-border flex flex-col min-h-0">
            <div className="px-3 py-2 text-sm font-medium text-text border-b border-border">活动流</div>
            <div className="flex-1 min-h-0">
              <ActivityStream taskId={taskId} />
            </div>
            <div className="h-[200px] border-t border-border">
              <TerminalPanel
                createSession={() => createTerminalSession(taskId)}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
