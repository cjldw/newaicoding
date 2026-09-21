/**
 * Runner Management API — react-query hooks (R16)
 * 错误码:
 *  - 16001: Runner 上有运行中的容器,不可删除
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
}

export interface CreateRunnerRequest {
  name: string
  role: 'worker' | 'deploy'
  max_containers: number
  public_ip?: string
}

export interface CreateRunnerResponse {
  runner_id: string
  name: string
  token: string
}

export interface ResetTokenResponse {
  token: string
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

// ---- API calls ----
export const runnersApi = {
  list: () => api.get<{ items: Runner[] }>('/admin/runners'),
  create: (data: CreateRunnerRequest) =>
    api.post<CreateRunnerResponse>('/admin/runners', data),
  resetToken: (runnerId: string) =>
    api.post<ResetTokenResponse>(`/admin/runners/${runnerId}/reset-token`),
  disable: (runnerId: string) =>
    api.post<{ message: string }>(`/admin/runners/${runnerId}/disable`),
  delete: (runnerId: string) =>
    api.delete<{ message: string }>(`/admin/runners/${runnerId}`),
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
