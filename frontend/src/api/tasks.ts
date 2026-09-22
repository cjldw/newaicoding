/**
 * Tasks API — 任务 CRUD + 对话/文件上传/下载 + react-query hooks
 * 错误码:
 *   4001 需求状态不允许创建该类型任务
 *   4002 用户未绑定 GitLab token
 *   4003 单项目并发 running 任务超限(>3)
 *   4004 文件超限(>50MB)
 *   4005 单次上传文件数超限(>10)
 *   4006 单任务累计上传超限(>200MB)
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from './client'
import { useAuthStore } from '@/stores/authStore'

// ---- Types ----
export type TaskType = 'requirement' | 'dev' | 'test' | 'release'
export type TaskStatus =
  | 'pending' | 'running' | 'done' | 'failed' | 'cancelled' | 'timeout' | 'cases_review'

export interface TaskUser {
  user_id: string
  username: string
  nickname: string
}

export interface TaskListItem {
  task_id: string
  type: TaskType
  title: string
  status: TaskStatus
  created_by: TaskUser
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface TaskListResponse {
  items: TaskListItem[]
  total: number
}

export interface TaskDetail {
  task_id: string
  type: TaskType
  title: string
  description: string
  status: TaskStatus
  base_branch: string
  work_branch: string
  container_id: string | null
  runner_id: string | null
  created_by: TaskUser
  started_at: string | null
  finished_at: string | null
  total_tokens_in: number
  total_tokens_out: number
  error_message: string | null
  last_commit_sha: string | null
}

export interface CreateTaskPayload {
  type: Exclude<TaskType, 'requirement'>
  title: string
  description: string
  base_branch?: string
  work_branch?: string
  deploy_port?: number
  deploy_host?: string
}

export interface TaskMessageFileRef {
  file_id: string
  filename: string
  container_path: string
  injected: boolean
}

export interface TaskMessage {
  message_id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  file_refs: TaskMessageFileRef[]
  tool_calls: unknown | null
  tokens_in: number
  tokens_out: number
  created_at: string
}

export interface TaskMessagesResponse {
  items: TaskMessage[]
}

export interface UploadedFile {
  file_id: string
  filename: string
  stored_filename: string
  size: number
  uploaded_by: TaskUser
  uploaded_at: string
}

export interface UploadedFilesResponse {
  items: UploadedFile[]
}

export interface UploadFileResponse {
  file_id: string
  filename: string
  stored_filename: string
  size: number
  container_path: string
}

// ---- Error message mapping ----
export function getTaskErrorMessage(code: number, fallback = '操作失败'): string {
  const map: Record<number, string> = {
    4001: '需求状态不允许创建该类型任务',
    4002: '请到个人设置绑定 GitLab token',
    4003: '项目并发任务数已达上限(3个)',
    4004: '文件大小超过 50MB',
    4005: '单次最多上传 10 个文件',
    4006: '单任务累计上传超过 200MB',
  }
  return map[code] ?? fallback
}

// ---- API functions ----
export async function fetchTasks(reqId: string): Promise<TaskListResponse> {
  const res = await api.get<TaskListResponse>(`/requirements/${reqId}/tasks`)
  return res.data
}

export async function createTask(
  reqId: string,
  payload: CreateTaskPayload,
): Promise<{ task_id: string }> {
  const res = await api.post<{ task_id: string }>(
    `/requirements/${reqId}/tasks`,
    payload,
  )
  return res.data
}

export async function fetchTaskDetail(taskId: string): Promise<TaskDetail> {
  const res = await api.get<TaskDetail>(`/tasks/${taskId}`)
  return res.data
}

export async function stopTask(taskId: string): Promise<void> {
  await api.post(`/tasks/${taskId}/stop`)
}

export async function retryTask(taskId: string): Promise<void> {
  await api.post(`/tasks/${taskId}/retry`)
}

export async function fetchTaskMessages(taskId: string): Promise<TaskMessagesResponse> {
  const res = await api.get<TaskMessagesResponse>(`/tasks/${taskId}/messages`)
  return res.data
}

export async function sendTaskMessage(
  taskId: string,
  content: string,
): Promise<{ message_id: string }> {
  const res = await api.post<{ message_id: string }>(
    `/tasks/${taskId}/messages`,
    { content },
  )
  return res.data
}

/** 上传单个文件(multipart) */
export async function uploadTaskFile(
  taskId: string,
  file: File,
): Promise<UploadFileResponse> {
  const token = useAuthStore.getState().token
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`/api/tasks/${taskId}/files/upload`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })
  const json = await res.json()
  if (json.code !== 0) throw new ApiError(json.code, json.message)
  return json.data
}

export async function fetchUploadedFiles(taskId: string): Promise<UploadedFilesResponse> {
  const res = await api.get<UploadedFilesResponse>(`/tasks/${taskId}/files/uploads`)
  return res.data
}

/** 下载文件(blob) */
export async function downloadTaskFile(taskId: string, fileId: string): Promise<Blob> {
  const token = useAuthStore.getState().token
  const res = await fetch(`/api/tasks/${taskId}/files/uploads/${fileId}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error('下载失败')
  return res.blob()
}

export async function deleteTaskFile(taskId: string, fileId: string): Promise<void> {
  await api.delete(`/tasks/${taskId}/files/uploads/${fileId}`)
}

/** 获取任务预览 URL(轮询用) */
export async function fetchTaskPreviews(taskId: string): Promise<{ url: string | null }> {
  const res = await api.get<{ url: string | null }>(`/tasks/${taskId}/previews`)
  return res.data
}

// ---- React Query hooks ----
export function useTaskList(reqId: string) {
  return useQuery({
    queryKey: ['tasks', reqId],
    queryFn: () => fetchTasks(reqId),
    enabled: !!reqId,
  })
}

export function useCreateTask(reqId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreateTaskPayload) => createTask(reqId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks', reqId] })
    },
  })
}

export function useTaskDetail(taskId: string) {
  return useQuery({
    queryKey: ['task', taskId],
    queryFn: () => fetchTaskDetail(taskId),
    enabled: !!taskId,
    refetchInterval: 5000,
  })
}

export function useStopTask(taskId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => stopTask(taskId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['task', taskId] }),
  })
}

export function useRetryTask(taskId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => retryTask(taskId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['task', taskId] }),
  })
}

export function useTaskMessages(taskId: string) {
  return useQuery({
    queryKey: ['task-messages', taskId],
    queryFn: () => fetchTaskMessages(taskId),
    enabled: !!taskId,
    refetchInterval: 3000,
  })
}

export function useSendTaskMessage(taskId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (content: string) => sendTaskMessage(taskId, content),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['task-messages', taskId] }),
  })
}

export function useUploadTaskFile(taskId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => uploadTaskFile(taskId, file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['task-uploads', taskId] }),
  })
}

export function useUploadedFiles(taskId: string) {
  return useQuery({
    queryKey: ['task-uploads', taskId],
    queryFn: () => fetchUploadedFiles(taskId),
    enabled: !!taskId,
  })
}

export function useDeleteTaskFile(taskId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (fileId: string) => deleteTaskFile(taskId, fileId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['task-uploads', taskId] }),
  })
}

export function useTaskPreviews(taskId: string) {
  return useQuery({
    queryKey: ['task-previews', taskId],
    queryFn: () => fetchTaskPreviews(taskId),
    enabled: !!taskId,
    refetchInterval: 5000,
  })
}
