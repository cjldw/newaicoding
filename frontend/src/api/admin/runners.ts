/**
 * Runner Management API — react-query hooks (R16 + R31 本机快速创建 + R32 标签管理与全字段编辑)
 * 错误码:
 *  - 16001: Runner 上有运行中的容器,不可删除(远程 runner)
 *  - 16002: 本机环境校验失败(message 细分,前端直显后端原文)
 *  - 16003: 本机 runner 上限(3)
 *  - 16004: 删除代停容器失败
 *  - 16005: 名称冲突
 *  - 16006: 非本机 runner 调 start/stop,或 disabled 启动
 *  - 16007: 停止时既无 WS 连接也无句柄
 *  - 16008: 任务类型标签非法(R32)
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../client'

// ---- Types ----
export interface RunnerMachineInfo {
  os: string
  arch: string
  cpu_count: number
  mem_total_gb: number
  docker_version: string
  // R16.F4(BUG-045):扩充字段——旧 runner 上报可能缺失,全部可选
  os_version?: string
  hostname?: string
  ip?: string
  cpu_model?: string
  disk_total_gb?: number
  disk_free_gb?: number
}

export interface Runner {
  runner_id: string
  name: string
  role: 'worker' | 'deploy'
  status: 'online' | 'offline' | 'disabled'
  last_heartbeat_at: string | null
  machine_info: RunnerMachineInfo | null
  current_containers: number
  max_containers: number
  public_ip: string | null
  created_at: string
  is_local: boolean // R31:本机快速创建标记
  tags: string[] // R32:任务类型标签(requirement/dev/test);空数组=兜底
}

// R32:任务类型标签选项(固定枚举)
export const TAG_OPTIONS = [
  { label: '需求', value: 'requirement' },
  { label: '开发', value: 'dev' },
  { label: '测试', value: 'test' },
] as const

export type TagValue = typeof TAG_OPTIONS[number]['value']

export interface CreateRunnerRequest {
  name: string
  role: 'worker' | 'deploy'
  max_containers: number
  public_ip?: string
  tags?: string[] // R32:任务类型标签
}

export interface CreateRunnerResponse {
  runner_id: string
  name: string
  token: string
}

export interface ResetTokenResponse {
  token: string
}

// R31:本机快速创建请求/响应
export interface CreateLocalRunnerRequest {
  name?: string // 留空自动生成 local-xxxxxxxx
  max_containers?: number // 默认 10
  tags?: string[] // R32:任务类型标签
}

export interface CreateLocalRunnerResponse {
  runner_id: string
  name: string
  status: 'online' | 'offline'
  token_hidden: true
  launch_command: {
    argv: string[]
    env_keys: string[]
  }
}

export interface LocalRunnerActionResponse {
  runner_id: string
  status: 'online' | 'offline'
}

// ---- Error codes ----
export const RunnerErrorCodes = {
  CONTAINER_RUNNING: 16001,
} as const

export function getRunnerErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 16001:
        return 'Runner 上有运行中的容器,不可删除'
      default:
        return error.message
    }
  }
  return '操作失败'
}

// R32:编辑 Runner 请求(全部可选,未传=不改动)
export interface UpdateRunnerRequest {
  name?: string
  max_containers?: number
  tags?: string[]
  public_ip?: string
}

// ---- API calls ----
export const runnersApi = {
  list: () => api.get<{ items: Runner[] }>('/admin/runners'),
  create: (data: CreateRunnerRequest) =>
    api.post<CreateRunnerResponse>('/admin/runners', data),
  // R31:本机快速创建(含启动)
  createLocal: (data: CreateLocalRunnerRequest) =>
    api.post<CreateLocalRunnerResponse>('/admin/runners/local', data),
  // R31:启动本机 runner
  start: (runnerId: string) =>
    api.post<LocalRunnerActionResponse>(`/admin/runners/${runnerId}/start`),
  // R31:停止本机 runner
  stop: (runnerId: string) =>
    api.post<LocalRunnerActionResponse>(`/admin/runners/${runnerId}/stop`),
  // R31:重启本机 runner
  restart: (runnerId: string) =>
    api.post<LocalRunnerActionResponse>(`/admin/runners/${runnerId}/restart`),
  resetToken: (runnerId: string) =>
    api.post<ResetTokenResponse>(`/admin/runners/${runnerId}/reset-token`),
  disable: (runnerId: string) =>
    api.post<{ message: string }>(`/admin/runners/${runnerId}/disable`),
  delete: (runnerId: string) =>
    api.delete<{ message: string }>(`/admin/runners/${runnerId}`),
  // R32:编辑 Runner(PATCH 部分更新)
  update: (runnerId: string, data: UpdateRunnerRequest) =>
    api.patch<Runner>(`/admin/runners/${runnerId}`, data),
}

// ---- React Query Hooks ----
export function useRunners() {
  return useQuery({
    queryKey: ['admin-runners'],
    queryFn: () => runnersApi.list().then(r => r.data.items),
  })
}

export function useCreateRunner() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateRunnerRequest) => runnersApi.create(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-runners'] }) },
  })
}

// R31:本机快速创建
export function useCreateLocalRunner() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateLocalRunnerRequest) => runnersApi.createLocal(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-runners'] }) },
  })
}

// R31:启动本机 runner
export function useStartRunner() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runnerId: string) => runnersApi.start(runnerId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-runners'] }) },
  })
}

// R31:停止本机 runner
export function useStopRunner() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runnerId: string) => runnersApi.stop(runnerId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-runners'] }) },
  })
}

// R31:重启本机 runner
export function useRestartRunner() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runnerId: string) => runnersApi.restart(runnerId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-runners'] }) },
  })
}

export function useResetRunnerToken() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runnerId: string) => runnersApi.resetToken(runnerId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-runners'] }) },
  })
}

export function useDisableRunner() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runnerId: string) => runnersApi.disable(runnerId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-runners'] }) },
  })
}

export function useDeleteRunner() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (runnerId: string) => runnersApi.delete(runnerId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-runners'] }) },
  })
}

// R32:编辑 Runner(PATCH 部分更新;invalidate 列表)
export function useUpdateRunner() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ runnerId, data }: { runnerId: string; data: UpdateRunnerRequest }) =>
      runnersApi.update(runnerId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-runners'] }) },
  })
}
