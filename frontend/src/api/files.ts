/**
 * Files API — 项目/任务模式文件操作 + WebSocket watcher
 * 项目模式:只读浏览 GitLab 仓库
 * 任务模式:读写 + 增删改 + Diff + 变更清单 + WS 实时推送
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useCallback } from 'react'
import { api } from './client'
import { useAuthStore } from '@/stores/authStore'

// ---- Types ----
export interface FileItem {
  path: string
  type: 'file' | 'dir'
  size: number
  mtime: string
}

export interface FileContent {
  path: string
  content: string
  encoding: string
}

export interface DiffFile {
  path: string
  status: 'modified' | 'added' | 'deleted' | 'renamed'
  diff: string
}

export interface ChangeFile {
  path: string
  status: 'M' | 'A' | 'D' | 'R'
  additions: number
  deletions: number
  old_path?: string // R 重命名时
}

export interface ChangeRepo {
  repo_id: string
  repo_role: 'main' | 'test' | 'docs' | 'other'
  files: ChangeFile[]
}

export interface ChangesResponse {
  total: number
  repos: ChangeRepo[]
}

export interface FileOperationRequest {
  operation: 'create' | 'delete' | 'rename'
  path: string
  new_path?: string
}

// ---- API calls ----
export const filesApi = {
  // 项目模式
  listProjectFiles: (projectId: string, branch: string, path: string) =>
    api.get<{ items: FileItem[] }>(
      `/projects/${projectId}/files?branch=${encodeURIComponent(branch)}&path=${encodeURIComponent(path)}`
    ),
  getProjectFileContent: (projectId: string, branch: string, path: string) =>
    api.get<FileContent>(
      `/projects/${projectId}/files/content?branch=${encodeURIComponent(branch)}&path=${encodeURIComponent(path)}`
    ),

  // 任务模式
  listTaskFiles: (taskId: string, path: string) =>
    api.get<{ items: FileItem[] }>(
      `/tasks/${taskId}/files?path=${encodeURIComponent(path)}`
    ),
  getTaskFileContent: (taskId: string, path: string) =>
    api.get<FileContent>(
      `/tasks/${taskId}/files/content?path=${encodeURIComponent(path)}`
    ),
  updateTaskFileContent: (taskId: string, path: string, content: string) =>
    api.put<{ message: string }>(
      `/tasks/${taskId}/files/content`,
      { path, content }
    ),
  fileOperation: (taskId: string, data: FileOperationRequest) =>
    api.post<{ message: string }>(
      `/tasks/${taskId}/files/operations`,
      data
    ),
  // R38:scope 口径切换(all=基线分支 vs 工作区;head=HEAD vs 工作区,缺省 all 向后兼容)
  getDiff: (taskId: string, scope: 'all' | 'head' = 'all') =>
    api.get<{ files: DiffFile[] }>(`/tasks/${taskId}/files/diff?scope=${scope}`),
  getChanges: (taskId: string, scope: 'all' | 'head' = 'all') =>
    api.get<ChangesResponse>(`/tasks/${taskId}/files/changes?scope=${scope}`),

  // R39:git 操作(commit/push)
  taskGitCommit: (taskId: string, message?: string) =>
    api.post<{ message: string; commit: string; author_name: string; author_email: string }>(
      `/tasks/${taskId}/git/commit`,
      { message }
    ),
  taskGitPush: (taskId: string) =>
    api.post<{ message: string; branch: string }>(`/tasks/${taskId}/git/push`),
}

// ---- React Query Hooks ----
export function useProjectFiles(projectId: string, branch: string, path: string) {
  return useQuery({
    queryKey: ['project-files', projectId, branch, path],
    queryFn: () => filesApi.listProjectFiles(projectId, branch, path).then(r => r.data),
    enabled: !!projectId,
  })
}

export function useProjectFileContent(projectId: string, branch: string, path: string) {
  return useQuery({
    queryKey: ['project-file-content', projectId, branch, path],
    queryFn: () => filesApi.getProjectFileContent(projectId, branch, path).then(r => r.data),
    enabled: !!projectId && !!path,
  })
}

export function useTaskFiles(taskId: string, path: string) {
  return useQuery({
    queryKey: ['task-files', taskId, path],
    queryFn: () => filesApi.listTaskFiles(taskId, path).then(r => r.data),
    enabled: !!taskId,
  })
}

export function useTaskFileContent(taskId: string, path: string) {
  return useQuery({
    queryKey: ['task-file-content', taskId, path],
    queryFn: () => filesApi.getTaskFileContent(taskId, path).then(r => r.data),
    enabled: !!taskId && !!path,
  })
}

export function useUpdateTaskFileContent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ taskId, path, content }: { taskId: string; path: string; content: string }) =>
      filesApi.updateTaskFileContent(taskId, path, content),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['task-file-content', variables.taskId, variables.path] })
    },
  })
}

export function useFileOperation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ taskId, data }: { taskId: string; data: FileOperationRequest }) =>
      filesApi.fileOperation(taskId, data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['task-files', variables.taskId] })
      qc.invalidateQueries({ queryKey: ['task-changes', variables.taskId] })
    },
  })
}

// R38:scope 口径入参,queryKey 带 scope → 切口径自动换 key refetch
export function useTaskDiff(taskId: string, scope: 'all' | 'head' = 'all') {
  return useQuery({
    queryKey: ['task-diff', taskId, scope],
    queryFn: () => filesApi.getDiff(taskId, scope).then(r => r.data),
    enabled: !!taskId,
  })
}

export function useTaskChanges(taskId: string, scope: 'all' | 'head' = 'all') {
  return useQuery({
    queryKey: ['task-changes', taskId, scope],
    queryFn: () => filesApi.getChanges(taskId, scope).then(r => r.data),
    enabled: !!taskId,
  })
}

// R39:git commit mutation — 成功后失效 diff/changes 双口径(R38 queryKey 带 scope,前缀失效覆盖 all+head)
export function useTaskGitCommit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ taskId, message }: { taskId: string; message?: string }) =>
      filesApi.taskGitCommit(taskId, message),
    onSuccess: (_data, variables) => {
      // 前缀失效:覆盖 task-diff/task-changes 两口径(all+head)
      qc.invalidateQueries({ queryKey: ['task-diff', variables.taskId] })
      qc.invalidateQueries({ queryKey: ['task-changes', variables.taskId] })
    },
  })
}

// R39:git push mutation — 成功后同样失效 diff/changes
export function useTaskGitPush() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (taskId: string) => filesApi.taskGitPush(taskId),
    onSuccess: (_data, taskId) => {
      qc.invalidateQueries({ queryKey: ['task-diff', taskId] })
      qc.invalidateQueries({ queryKey: ['task-changes', taskId] })
    },
  })
}

// ---- WebSocket watcher ----
export interface FileWatcherMessage {
  type: 'file_changed' | 'file_deleted'
  path: string
  content?: string
}

export function useTaskFileWatcher(
  taskId: string | null,
  onMessage?: (msg: FileWatcherMessage) => void
) {
  const wsRef = useRef<WebSocket | null>(null)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  const connect = useCallback(() => {
    if (!taskId) return

    const token = useAuthStore.getState().token
    if (!token) return

    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/tasks/${taskId}/files?token=${token}`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const msg: FileWatcherMessage = JSON.parse(event.data)
        onMessageRef.current?.(msg)
      } catch (err) {
        console.error('[FileWatcher] parse error:', err)
      }
    }

    ws.onerror = (err) => {
      console.error('[FileWatcher] error:', err)
    }

    ws.onclose = () => {
      // 5s 后重连
      setTimeout(() => {
        if (wsRef.current === ws) {
          connect()
        }
      }, 5000)
    }
  }, [taskId])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect])
}
